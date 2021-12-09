# edge-probe

## Citation
If you use our code for academic work, please cite:

```
@inproceedings{fayyaz-etal-2021-models,
    title = "Not All Models Localize Linguistic Knowledge in the Same Place: A Layer-wise Probing on {BERT}oids{'} Representations",
    author = "Fayyaz, Mohsen  and
      Aghazadeh, Ehsan  and
      Modarressi, Ali  and
      Mohebbi, Hosein  and
      Pilehvar, Mohammad Taher",
    booktitle = "Proceedings of the Fourth BlackboxNLP Workshop on Analyzing and Interpreting Neural Networks for NLP",
    month = nov,
    year = "2021",
    address = "Punta Cana, Dominican Republic",
    publisher = "Association for Computational Linguistics",
    url = "https://aclanthology.org/2021.blackboxnlp-1.29",
    pages = "375--388",
    abstract = "Most of the recent works on probing representations have focused on BERT, with the presumption that the findings might be similar to the other models. In this work, we extend the probing studies to two other models in the family, namely ELECTRA and XLNet, showing that variations in the pre-training objectives or architectural choices can result in different behaviors in encoding linguistic information in the representations. Most notably, we observe that ELECTRA tends to encode linguistic knowledge in the deeper layers, whereas XLNet instead concentrates that in the earlier layers. Also, the former model undergoes a slight change during fine-tuning, whereas the latter experiences significant adjustments. Moreover, we show that drawing conclusions based on the weight mixing evaluation strategy{---}which is widely used in the context of layer-wise probing{---}can be misleading given the norm disparity of the representations across different layers. Instead, we adopt an alternative information-theoretic probing with minimum description length, which has recently been proven to provide more reliable and informative results.",
}
```
