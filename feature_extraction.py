# -*- coding: utf-8 -*-
"""Feature Extraction.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1qI8RfD_Dk0A_UZcnaO_83EJ3i0oPMaSp

# Installations
"""

# from IPython.display import clear_output
# ! nvidia - smi
# ! pip install datasets transformers
# clear_output()

from datasets import load_dataset, load_metric
from transformers import AutoTokenizer
import torch.nn as nn
import torch.optim as optim
from tqdm.auto import tqdm
import torch
import numpy as np
import random
import matplotlib.pyplot as plt
import json
import sys
import sentencepiece
# ! pip install diskcache
import diskcache as dc
import shutil

shutil.rmtree('cache_tmp', ignore_errors=True)
cache = dc.Cache('cache_tmp', size_limit=int(40e9))
# cache['key'] = torch.zeros((13, 768))
# %timeit cache['key']

"""# Config"""
GLUE_TASKS = ["cola", "mnli", "mnli-mm", "mrpc", "qnli", "qqp", "rte", "sst2", "stsb", "wnli"]
task = "mnli"
# model_checkpoint = "distilbert-base-uncased"
# model_checkpoint = "albert-base-v2"
# model_checkpoint = "bert-base-uncased"
# model_checkpoint = "xlnet-base-cased"
# model_checkpoint = "google/electra-base-discriminator"
# model_checkpoint = "howey/electra-base-cola"
model_checkpoint = "TehranNLP-org/bert-base-uncased-avg-mnli-2e-5-21"
batch_size = 32
LEARNING_RATE = 5e-4
MAX_LENGTH = 128

fine_tune_to_layer = None  # [0, end] 0 -> just embedding / 12 -> no freezing
POOLING_METHODS = ["cls", "words_avg", "words_max", "avg"]
pooling_method = "avg"
SEED = 0

model_checkpoint = sys.argv[1]
task = sys.argv[2]
SEED = int(sys.argv[3])

DEVICE = 'cuda' if torch.cuda.is_available() else "cpu"
print(DEVICE)


def set_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


set_seed(SEED)
"""# Preprocessing

"""

actual_task = "mnli" if task == "mnli-mm" else task
num_labels = 3 if task.startswith("mnli") else 1 if task == "stsb" else 2
dataset = load_dataset("glue", actual_task)
metric = load_metric('glue', actual_task)
metric_name = "pearson" if task == "stsb" else "matthews_correlation" if task == "cola" else "accuracy"

task_to_keys = {
    "cola": ("sentence", None),
    "mnli": ("premise", "hypothesis"),
    "mnli-mm": ("premise", "hypothesis"),
    "mrpc": ("sentence1", "sentence2"),
    "qnli": ("question", "sentence"),
    "qqp": ("question1", "question2"),
    "rte": ("sentence1", "sentence2"),
    "sst2": ("sentence", None),
    "stsb": ("sentence1", "sentence2"),
    "wnli": ("sentence1", "sentence2"),
}
sentence1_key, sentence2_key = task_to_keys[task]
validation_key = "validation_mismatched" if task == "mnli-mm" else "validation_matched" if task == "mnli" else "validation"
dataset["validation"] = dataset[validation_key]
print(dataset)
print(dataset["validation"][0])


class Utils:
    def one_hot(idx: int, length):
        import numpy as np
        o = np.zeros(length, dtype=np.int8)
        o[idx] = 1
        return o

    def one_hot_batch(idxs: list, length):
        import numpy as np
        for i in range(len(idxs)):
            o = np.zeros(length, dtype=np.int8)
            o[idxs[i]] = 1
            idxs[i] = o
        return np.array(idxs)


tokenizer = AutoTokenizer.from_pretrained(model_checkpoint, use_fast=True)


def preprocess_function(examples):
    examples["label"] = Utils.one_hot_batch(examples["label"], num_labels)
    if sentence2_key is None:
        t1 = tokenizer(examples[sentence1_key], truncation=True, padding=True, max_length=MAX_LENGTH)
    else:
        t1 = tokenizer(examples[sentence1_key], examples[sentence2_key], truncation=True, padding=True,
                       max_length=MAX_LENGTH)
    return t1


encoded_dataset = dataset.map(preprocess_function, batched=True, batch_size=batch_size)

print(dataset["validation"][55])
print(encoded_dataset["train"][2])
print(tokenizer.decode(encoded_dataset["train"][2]["input_ids"]))

# print(tokenizer.get_special_tokens_mask(encoded_dataset["train"][2]["input_ids"], already_has_special_tokens=True))

"""# Classification

"""

from transformers import AutoModelForSequenceClassification, AutoModel

# model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint, num_labels=num_labels)
model = AutoModelForSequenceClassification.from_pretrained(model_checkpoint)
model.save_pretrained(model_checkpoint)
tokenizer.save_pretrained(model_checkpoint)
print(model)

from abc import ABC, abstractmethod


class ReprsPooling(ABC, nn.Module):
    def __init__(self, model_checkpoint):
        super(ReprsPooling, self).__init__()
        self.model_checkpoint = model_checkpoint

    @abstractmethod
    def forward(self, hidden_states, special_tokens_mask):
        """
        input:
            hidden_states: [batch_size, layers, max_span_len, embedding_dim] ~ [32, 13, 15, 768]
            special_tokens_mask: [batch_size, max_span_len]
        returns:
            [13, 16, 768]
        """
        raise NotImplementedError


class ReprsPoolingCls(ReprsPooling):
    def forward(self, hidden_states, special_tokens_mask):
        if "xlnet" in model_checkpoint:
            cls_index = -1
        else:
            cls_index = 0
        current_hidden_states = torch.stack([val[:, cls_index, :].detach() for val in hidden_states])
        return current_hidden_states


class ReprsPoolingWordsAvg(ReprsPooling):
    def forward(self, hidden_states, special_tokens_mask):
        word_tokens_mask = torch.logical_not(special_tokens_mask)  # ~[16, 19]
        current_hidden_states = torch.stack([val[:, :, :].detach() for val in hidden_states])  # ~[13, 16, 19, 768]
        span_masks_shape = word_tokens_mask.shape
        span_masks = word_tokens_mask.reshape(
            1,
            span_masks_shape[0],
            span_masks_shape[1],
            1
        ).expand_as(current_hidden_states)
        attention_spans = current_hidden_states * span_masks
        sum = torch.sum(attention_spans, dim=-2)  # ~[13, 16, 768]
        num_words_in_batch = torch.count_nonzero(word_tokens_mask, dim=-1).reshape(1, -1, 1).expand_as(
            sum)  # ~[13, 16, 768]
        avg_span_repr = sum / num_words_in_batch
        return avg_span_repr


class ReprsPoolingAvg(ReprsPooling):
    def forward(self, hidden_states, attention_mask):
        current_hidden_states = torch.stack([val[:, :, :].detach() for val in hidden_states])  # ~[13, 16, 19, 768]

        span_masks_shape = attention_mask.shape
        span_masks = attention_mask.reshape(
            1,
            span_masks_shape[0],
            span_masks_shape[1],
            1
        ).expand_as(current_hidden_states)
        attention_spans = current_hidden_states * span_masks
        sum = torch.sum(attention_spans, dim=-2)  # ~[13, 16, 768]
        num_words_in_batch = torch.count_nonzero(attention_mask, dim=-1).reshape(1, -1, 1).expand_as(
            sum)  # ~[13, 16, 768]
        avg_span_repr = sum / num_words_in_batch

        return avg_span_repr


class ReprsPoolingWordsMax(ReprsPooling):
    def forward(self, hidden_states, special_tokens_mask):
        word_tokens_mask = torch.logical_not(special_tokens_mask).float()
        current_hidden_states = torch.stack([val[:, :, :].detach() for val in hidden_states])  # ~[13, 16, 19, 768]

        span_masks_shape = word_tokens_mask.shape
        span_masks = word_tokens_mask.reshape(
            1,
            span_masks_shape[0],
            span_masks_shape[1],
            1
        ).expand_as(current_hidden_states)
        attention_spans = current_hidden_states * span_masks - 1e10 * (1 - span_masks)

        max_span_repr, max_idxs = torch.max(attention_spans, dim=-2)
        return max_span_repr


def get_pooling_module(model_checkpoint, method="cls"):
    if method == "cls":
        return ReprsPoolingCls(model_checkpoint)
    elif method == "words_avg":
        return ReprsPoolingWordsAvg(model_checkpoint)
    elif method == "words_max":
        return ReprsPoolingWordsMax(model_checkpoint)
    elif method == "avg":
        return ReprsPoolingAvg(model_checkpoint)
    else:
        raise Exception("Unknown Pooling Method!")


class Classifier(nn.Module):
    def __init__(self, model_checkpoint, num_labels, device='cuda'):
        super(Classifier, self).__init__()
        self.model_classifier = self.get_model_classifier(model_checkpoint, num_labels)
        # self.training_criterion = nn.BCELoss()
        self.training_criterion = nn.BCEWithLogitsLoss()

    def forward(self, cls_embedding):
        preds = self.model_classifier(cls_embedding)
        # preds = nn.Sigmoid()(preds)
        return preds

    def get_model_classifier(self, model_checkpoint, num_labels):
        if model_checkpoint == "distilbert-base-uncased":
            return nn.Sequential(
                nn.Linear(in_features=768, out_features=768, bias=True),
                nn.Linear(in_features=768, out_features=num_labels, bias=True),
                nn.Dropout(p=0.2, inplace=False),
            )
        elif "albert-base-v2" in model_checkpoint:
            return nn.Sequential(
                nn.Linear(in_features=768, out_features=768, bias=True),
                nn.Linear(in_features=768, out_features=num_labels, bias=True),
                nn.Dropout(p=0.2, inplace=False),
            )
        elif "bert-base-uncased" in model_checkpoint:
            return nn.Sequential(
                nn.Linear(in_features=768, out_features=768, bias=True),
                nn.Tanh(),
                nn.Dropout(p=0.1, inplace=False),
                nn.Linear(in_features=768, out_features=num_labels, bias=True)
            )
        elif "xlnet-base-cased" in model_checkpoint:
            return nn.Sequential(
                nn.Linear(in_features=768, out_features=768, bias=True),
                nn.Identity(),
                nn.Dropout(p=0.1, inplace=False),
                nn.Linear(in_features=768, out_features=num_labels, bias=True)
            )
        elif "electra" in model_checkpoint:
            return nn.Sequential(
                nn.Linear(in_features=768, out_features=768, bias=True),
                nn.Dropout(p=0.1, inplace=False),
                nn.Linear(in_features=768, out_features=num_labels, bias=True)
            )
        else:
            raise Exception(f"No Classifier Defined for {model_checkpoint}")


class Trainer:
    def __init__(self, model_checkpoint, num_labels, encoded_dataset, language_model, metric, device='cuda',
                 num_layers=13, pooling_method="cls", save_address="history.pkl"):
        self.model_checkpoint = model_checkpoint
        self.num_labels = num_labels
        self.device = device
        self.encoded_dataset = encoded_dataset
        self.language_model = language_model
        self.language_model.config.output_hidden_states = True
        self.language_model.to(device)
        self.pooling = get_pooling_module(model_checkpoint, pooling_method)
        self.num_layers = num_layers
        self.metric = metric
        self.save_address = save_address

        # CLASSIFIERS & OPTIMIZERS
        print("Creating New Classifiers")
        self.classifiers = []
        self.optimizers = []
        for i in range(num_layers):
            classifier = Classifier(model_checkpoint, num_labels, device)
            classifier.to(self.device)
            self.classifiers.append(classifier)
            params = classifier.parameters()
            self.optimizers.append(optim.Adam(params, lr=LEARNING_RATE, weight_decay=0))

        self.history = ({
            "loss": {"train": [], "dev": [], "test": []},
            "metrics":
                {"glue_metric": {"dev": [], "test": []}}
        })

    def train(self, batch_size, epochs=3):
        self.batch_size = batch_size
        train_dataset = self.encoded_dataset["train"]
        dataset_len = len(train_dataset)
        print("#########################################################")
        print(f"Train on {dataset_len} Samples")
        for epoch in range(epochs):
            self.language_model.train()
            running_loss = 0.0
            steps = 0
            for classifier in self.classifiers:
                classifier.train()
            print("#########################################################")
            for i in tqdm(range(0, dataset_len, batch_size), desc=f"[Epoch {epoch + 1}/{epochs}]"):
                step = batch_size
                if i + batch_size > dataset_len:
                    step = dataset_len - i

                labels = torch.tensor(train_dataset[i: i + step]["label"]).float().to(self.device)
                with torch.no_grad():
                    pooled_hidden_states = self.extract_pooled_embedding(train_dataset, i, i + step, train=True)
                for layer_idx, classifier in enumerate(self.classifiers):
                    self.optimizers[layer_idx].zero_grad()
                    outputs = classifier(pooled_hidden_states[layer_idx, :, :])
                    loss = classifier.training_criterion(outputs.to(self.device), labels)
                    loss.backward()
                    # torch.nn.utils.clip_grad_norm_(edge_probe_model.parameters(), 5.0)
                    self.optimizers[layer_idx].step()
                    running_loss += loss.item()
                    steps += 1

            self.update_history(epoch + 1, train_loss=running_loss / steps)
            self.plot_history(epoch)
            print(self.history)

    def extract_pooled_embedding(self, train_dataset, start_idx, end_idx, train=True):
        if train == True:
            key = f"train_{start_idx}-{end_idx}"
        else:
            key = f"test_{start_idx}-{end_idx}"

        if key not in cache:
            tokenized_input = train_dataset[start_idx: end_idx]
            tokenized_input_ids = torch.tensor(tokenized_input["input_ids"]).to(self.device)
            # special_tokens_mask = torch.tensor(tokenized_input["special_tokens_mask"]).to(self.device)
            attention_mask = torch.tensor(tokenized_input["attention_mask"]).to(self.device)
            token_type_ids = torch.tensor(tokenized_input["token_type_ids"]).to("cuda")

            self.language_model.eval()
            outputs = self.language_model(input_ids=tokenized_input_ids, attention_mask=attention_mask, token_type_ids=token_type_ids)
            current_hidden_states = self.pooling(outputs.hidden_states, attention_mask)
            cache[key] = current_hidden_states
        else:
            current_hidden_states = cache[key]
        return current_hidden_states

    def compute_metrics(self, predictions, labels):
        if task != "stsb":
            predictions = np.argmax(predictions, axis=1)
        else:
            predictions = predictions[:, 0]
        metric_values = self.metric.compute(predictions=predictions, references=labels)
        for key, value in metric_values.items():
            self.history["glue_metric_name"] = key
            final_value = value
        return final_value

    def calc_loss(self, tokenized_dataset, desc=""):
        batch_size = self.batch_size
        for classifier in self.classifiers:
            classifier.eval()

        with torch.no_grad():
            running_loss = 0
            dataset_len = len(tokenized_dataset["input_ids"])
            steps = 0
            preds = [None] * self.num_layers
            metric_value = [None] * self.num_layers
            for i in tqdm(range(0, dataset_len, batch_size), desc=desc):
                step = batch_size
                if i + batch_size > dataset_len:
                    step = dataset_len - i

                labels = torch.tensor(tokenized_dataset[i: i + step]["label"]).float().to(self.device)
                pooled_hidden_states = self.extract_pooled_embedding(tokenized_dataset, i, i + step, train=False)
                for layer_idx, classifier in enumerate(self.classifiers):
                    outputs = classifier(pooled_hidden_states[layer_idx, :, :])
                    preds[layer_idx] = outputs if i == 0 else torch.cat((preds[layer_idx], outputs), 0)
                    loss = classifier.training_criterion(outputs.to(self.device), labels)
                    running_loss += loss.item()
                    steps += 1

        y_true = np.array(tokenized_dataset["label"]).argmax(-1)
        for idx, pred in enumerate(preds):
            pred = pred.cpu()
            metric_value[idx] = self.compute_metrics(pred, y_true)

        return running_loss / steps, metric_value

    def update_history(self, epoch, train_loss):
        # val_name = "validation_matched" if "mnli" in task else "validation"
        dev_loss, dev_f1 = self.calc_loss(self.encoded_dataset["validation"], desc="Dev Loss")
        # test_loss, test_f1 = self.calc_loss(self.encoded_dataset["test"], desc="Test Loss")
        test_loss, test_f1 = dev_loss, dev_f1
        self.history["loss"]["train"].append(train_loss)
        self.history["loss"]["dev"].append(dev_loss)
        self.history["loss"]["test"].append(test_loss)
        self.history["metrics"]["glue_metric"]["dev"].append(dev_f1)
        self.history["metrics"]["glue_metric"]["test"].append(test_f1)
        # self.history["layers_weights"].append(self.edge_probe_model.weighing_params.tolist())
        print('[%d] loss:' % (epoch))
        print("Train Loss:", self.history["loss"]["train"][-1])
        print("Dev Loss:", self.history["loss"]["dev"][-1])
        print("Test Loss:", self.history["loss"]["test"][-1])
        self.save_history(self.history)

    def plot_history(self, epoch):
        print("Loss History")
        loss_history = self.history["loss"]
        x = range(len(loss_history["train"]))
        plt.plot(x, loss_history["train"])
        plt.plot(x, loss_history["dev"])
        plt.plot(x, loss_history["test"])
        plt.ylabel('Loss')
        plt.xlabel('Epoch')
        plt.legend(['Train', 'Dev', 'Test'], loc='lower left')
        plt.show()

        w = np.max(self.history["metrics"]["glue_metric"]["dev"], axis=-2)
        plt.bar(np.arange(len(w), dtype=int), w)
        plt.ylabel(self.history["glue_metric_name"])
        plt.xlabel('Layer')
        plt.title("Best Result")
        plt.show()

        glue_history = self.history["metrics"]["glue_metric"]["dev"]
        x = range(len(glue_history))
        for i in range(len(glue_history[0])):
            plt.plot(x, np.array(glue_history)[:, i])
        plt.ylabel(self.history["glue_metric_name"])
        plt.xlabel('Epoch')
        plt.legend(range(13), loc='lower left')
        plt.show()

    def save_history(self, history_dict):
        file_name = "feature_extraction/feature_" + model_checkpoint + "_" + task + "_" + str(SEED)
        history_dict["Model"] = model_checkpoint,
        history_dict["Batch Size"] = batch_size,
        history_dict["Learning Rate"] = LEARNING_RATE,
        history_dict["seed"] = SEED
        history_dict["probe_summary"] = str(trainer.classifiers[0])
        history_dict["dataset_name"] = task
        history_dict["dataset_statistics"] = str(self.encoded_dataset)
        history_dict["max_len"] = MAX_LENGTH

        from pathlib import Path
        Path(file_name).mkdir(parents=True, exist_ok=True)
        with open(f"{file_name}.json", "w") as json_file:
            json.dump(history_dict, json_file, indent=4)

    def summary(self):
        pytorch_total_params = sum(p.numel() for p in self.classifiers[0].parameters())
        pytorch_total_params_trainable = sum(p.numel() for p in self.classifiers[0].parameters() if p.requires_grad)
        print("Total Parameters:    ", pytorch_total_params)
        print("Trainable Parameters:", pytorch_total_params_trainable)
        print(trainer.classifiers[0])


trainer = Trainer(model_checkpoint, num_labels, encoded_dataset, model, metric, DEVICE, pooling_method=pooling_method)

trainer.summary()

trainer.train(batch_size, epochs=50)
