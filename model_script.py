# -*- coding: utf-8 -*-
"""model_script.ipynb

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/1Gs3Yt6sd-cGCt3OunWdLeN1FMEVEBzCT
"""

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from FlagEmbedding import BGEM3FlagModel
import numpy as np
import os
import pandas as pd
import pickle
from sklearn.metrics import f1_score
from copy import deepcopy
import torch.nn.functional as F
from datasets import Dataset
import ast
import math

import os
os.chdir(r'<Specify working directory>')

#read in dataset to be predicted - Note, this data should have already been translated to English and processed by ChatGPT
dat=pd.read_excel('model-es/data/wi_dataset_chatgpt_full.xlsx')
print(dat.shape)

#Run Job Title normalisation and Job duties extraction using Gemma-2b LLM fine-tuned using SFT
from peft import AutoPeftModelForCausalLM
import re
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
import pandas as pd
import os
from datasets import Dataset
from sklearn.model_selection import train_test_split

#set working directory
os.chdir(r'C:\Program Files\Anaconda3\envs\mrsdautocoder\model-es')

#load job duties summarisation model - This refers to a Gemma-2b model fine-tuned via TRL
model_directory = 'gemma job duties summarisation'
peft_model = AutoPeftModelForCausalLM.from_pretrained(
    model_directory,
    device_map='auto',
    torch_dtype=torch.bfloat16
)
peft_model = peft_model.to('cuda')
tokenizer = AutoTokenizer.from_pretrained(model_directory)

#construct HF data object
ds = Dataset.from_dict({
    'title':dat['title'].astype(str),
    'description':dat['job_duties_abstractive'].astype(str)
})

def get_token_length(batch):
    #get token length in isco_title
    title_len = [len(i) for i in tokenizer(batch['title'])['input_ids']]
    duties_len = [len(i) for i in tokenizer(batch['description'])['input_ids']]
    return {
        'title_length':title_len,
        'duties_length':duties_len,
    }

ds_ = ds.map(get_token_length,batched=True)

print(max(ds_['title_length']))
print(max(ds_['duties_length']))

#define functions to aid job title normalisation and job duties summarisation
def get_prediction(example, instruct_prompt, model, task):
    if task=='jt_normalisation':
        example_list = [f"<bos>f'<start_of_turn>user {instruct_prompt}{title}\n\njob_duties: {description}<end_of_turn>" + \
        f"<start_of_turn>model\n" for title,description in zip(example['job_title'],example['job_duties'])]
        input_ = tokenizer(example_list,
                      return_tensors='pt',add_special_tokens=False,
                           truncation=True,
                           padding=True,pad_to_multiple_of = 8,
                          max_length=256).to('cuda')
        out = model.generate(**input_,max_new_tokens=32)
        result = tokenizer.batch_decode(out,skip_special_tokens=False)
        example['result']=[re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i).group(1) if \
                           re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i) is not None else 'ERROR' for i in result]
        #clear gc memory
        del example_list
        del out
        del input_
        del result
        torch.cuda.empty_cache()
        return example

    elif task=='jd_summarisation':
        example_list = [f'<bos><start_of_turn>user {instruct_prompt}{i}<end_of_turn>' + \
        f"<start_of_turn>model\n" for i in example['job_duties']]
        input_ = tokenizer(example_list,
                      return_tensors='pt',add_special_tokens=False,truncation=True,
                           padding=True, pad_to_multiple_of = 8,
                          max_length=3200).to('cuda')
        out = model.generate(**input_,max_new_tokens=256)
        result = tokenizer.batch_decode(out,skip_special_tokens=False)
        example['result']=[re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i).group(1) if \
                           re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i) is not None else 'ERROR' for i in result]
        #clear gc memory
        del example_list
        del out
        del input_
        del result
        torch.cuda.empty_cache()
        return example
    elif task=='industry_extraction':
        example_list = [f"<bos>f'<start_of_turn>user {instruct_prompt}{title}\n\njob_duties: {description}<end_of_turn>" + \
        f"<start_of_turn>model\n" for title,description in zip(example['job_title'],example['job_duties'])]
        input_ = tokenizer(example_list,
                      return_tensors='pt',add_special_tokens=False,
                           truncation=True,
                           padding=True,pad_to_multiple_of = 8,
                          max_length=256).to('cuda')
        out = model.generate(**input_,max_new_tokens=32)
        result = tokenizer.batch_decode(out,skip_special_tokens=False)
        example['result']=[re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i).group(1) if \
                           re.search(r'<start_of_turn>model\n(.*?)<end_of_turn>', i) is not None else 'ERROR' for i in result]
        #clear gc memory
        del example_list
        del out
        del input_
        del result
        torch.cuda.empty_cache()
        return example

def get_result(df, model, task, batch_size):
    if task=='jt_normalisation':
        instruct_prompt = "Below is an instruction that describes a task. Write a response that appropriately completes the request. \n\nWith reference to the summarised job_duties, normalise the following job title: "
        #create input
        ds = Dataset.from_dict({
            'job_title':df['job_title'].tolist(),
            'job_duties':df['job_duties_summarised'].tolist()
        })
        ds = ds.map(get_prediction,
                   fn_kwargs={
                       'model':model,
                       'instruct_prompt':instruct_prompt,
                       'task':task
                   },batched=True,batch_size=batch_size)
        return ds
    elif task=='jd_summarisation':
        instruct_prompt = "Below is an instruction that describes a task. Write a response that appropriately completes the request. \n\nSummarise the following job duties: "
        #create input
        ds = Dataset.from_dict({
            'job_duties':df['job_duties'].tolist(),
        })
        ds = ds.map(get_prediction,
                   fn_kwargs={
                       'model':model,
                       'instruct_prompt':instruct_prompt,
                       'task':task
                   },batched=True,batch_size=batch_size)
        return ds
    elif task=='industry_extraction':
        instruct_prompt = "Below is an instruction that describes a task. Write a response that appropriately completes the request. \n\nWith reference to the job title and job duties, identify the most likely industry and specialisation:  "
        #create input
        ds = Dataset.from_dict({
            'job_title':df['job_title_normalised'].tolist(),
            'job_duties':df['job_duties_summarised'].tolist(),
        })
        ds = ds.map(get_prediction,
                   fn_kwargs={
                       'model':model,
                       'instruct_prompt':instruct_prompt,
                       'task':task
                   },batched=True,batch_size=batch_size)
        return ds

#construct HF dataset object from file
dat.rename(columns={
    'title':'job_title',
    'description':'job_duties'
},inplace=True)

#fill na with blanks
dat.fillna(
    value = {
        'job_title':'',
        'job_duties':''
    },
    inplace=True
)
#lower case and title case
#change variable types - proper casing
dat['job_title'] = dat['job_title'].astype(str).str.title()
dat['job_duties'] = dat['job_duties'].astype(str).str.lower()

#pass object to get_result helper function to obtain summarised job duties
ds = get_result(dat,peft_model,task='jd_summarisation',batch_size=16)
dat['job_duties_summarised'] = ds.to_pandas()['result'].tolist()

#load job title normalisation model - This refers to a gemma2b model fine-tuned via TRL
model_directory = 'gemma job title normalisation'
tokenizer = AutoTokenizer.from_pretrained(model_directory)
peft_model = AutoPeftModelForCausalLM.from_pretrained(
    model_directory,
    device_map='auto',
    torch_dtype=torch.bfloat16
)
peft_model = peft_model.to('cuda')
#pass object to get_result helper function to obtain summarised job duties
ds = get_result(dat,peft_model,task='jt_normalisation',batch_size=128)
dat['job_title_normalised'] = ds.to_pandas()['result'].tolist()

#dat now contains job_title_normalised and job_duties_summarised which would be predicted by ISCO autocoder

#load job title normalisation model - This refers to a gemma2b model fine-tuned via TRL
model_directory = 'gemma industry extraction'
peft_model = AutoPeftModelForCausalLM.from_pretrained(
    model_directory,
    device_map='auto',
    torch_dtype=torch.bfloat16
)
peft_model = peft_model.to('cuda')
#pass object to get_result helper function to obtain summarised job duties
ds = get_result(dat,peft_model,task='industry_extraction',batch_size=8)
dat['industry_specialisation'] = ds.to_pandas()['result'].tolist()

###Training of ISCO autoocder model###

#reading in datasets (these datasets were created using a combination of wi_labels.csv,\
#isco codebook, synthetic data generated from chatgpt, open source web data from LinkedIn. \
#These datasets were processed using chatgpt40-mini to extract out the normalised job titles, \
#summarised job duties and industry/specialisation)

X_ = pd.read_excel('model-es/datav2/training_set_141024.xlsx')
X_val = pd.read_excel('model-es/datav2/test_set_141024.xlsx')

#replace any blanks with ''
X_.fillna('',inplace=True)
X_val.fillna('',inplace=True)

#lower case and title case titles and duties respectively
X_['isco_title'] = X_['isco_title'].str.title()
X_val['isco_title'] = X_val['isco_title'].str.title()

#industry
X_['isco_industry'] = X_['isco_industry'].str.title()
X_val['isco_industry'] = X_val['isco_industry'].str.title()
#duties
X_['isco_duties'] = X_['isco_duties'].str.lower()
X_val['isco_duties'] = X_val['isco_duties'].str.lower()

#create title + duties field
X_['isco_title_duties'] = 'job title= ' + X_['isco_title'] + '| job duties= ' + X_['isco_duties']
X_val['isco_title_duties'] = 'job title= ' + X_val['isco_title'] + '| job duties= ' + X_val['isco_duties']

#title + duties + industry field
X_['isco_title_duties_industry'] = 'job title= ' + X_['isco_title'] + '| job duties= ' + X_['isco_duties'] + \
'| industry|specialisation= ' + X_['isco_industry']

X_val['isco_title_duties_industry'] = 'job title= ' + X_val['isco_title'] + '| job duties= ' + X_val['isco_duties'] + \
'| industry|specialisation= ' + X_val['isco_industry']

vc_table = X_['isco_code'].value_counts().reset_index()

#given the severe class imbalance, we under/over-sample the majority and minority classes
vc_table['count'].describe()

X_.columns

X_train = X_.drop(labels='isco_code',axis=1)
y_train = X_['isco_code']

us_table = vc_table.loc[vc_table['count']>=500]
us_table['sample_count']=500
us_dict = dict(zip(us_table['isco_code'],us_table['sample_count']))

import math
os_dict = vc_table.loc[vc_table['count']<=100]
os_dict['sample_count']= [math.ceil(math.sqrt(i)) for i in 100-os_dict['count']] #number to oversample by
os_dict['sample_count'] = os_dict['count'] + os_dict['sample_count'] #total number of samples required
os_dict = dict(zip(os_dict['isco_code'],os_dict['sample_count']))

#append in synthetic data for code
#adopt the use of the imblearn library
from imblearn.over_sampling import RandomOverSampler
from imblearn.under_sampling import RandomUnderSampler
rus = RandomUnderSampler(random_state=42, sampling_strategy=us_dict)
ros = RandomOverSampler(random_state=42, sampling_strategy=os_dict)
X_,y_ = rus.fit_resample(X_train,y_train)
X_,y_ = ros.fit_resample(X_,y_)

X_ = pd.concat([X_,y_],axis=1)

#pre-process target variable
X_.isco_code = X_.isco_code.astype(str)
X_['isco_code']=[('0' + i) if len(i)==3 else i for i in X_.isco_code]
X_val.isco_code = X_val.isco_code.astype(str)
X_val['isco_code']=[('0' + i) if len(i)==3 else i for i in X_val.isco_code]

#construct isco_code 4D variable for both train and test
X_['isco_code_4d'] = [i[:4] for i in X_['isco_code']]
X_val['isco_code_4d'] = [i[:4] for i in X_val['isco_code']]

dat = X_
val = X_val

print(dat.shape)
print(val.shape)

set(dat.isco_code).difference(set(val.isco_code)) #should yield empty set

#convert to numerical value using label encoder and store label encoder for use later during decoding
from sklearn.preprocessing import LabelEncoder
le_4d = LabelEncoder()

dat['isco_code_4d'] = le_4d.fit_transform(dat.isco_code_4d.tolist())

#apply it to val
val['isco_code_4d'] = le_4d.transform(val.isco_code_4d.tolist())

#save label encoder as a .pkl file for future use
pickle.dump(le_4d,open('model-es/classification bge v5/labelencoder_4d.pkl','wb'))

#generate embeddings for text provided using BGE - utilise HF dataset for batch processing
from datasets import Dataset
ds = Dataset.from_dict({
    'isco_title':dat.isco_title,
    'isco_duties':dat.isco_duties,
    'isco_title_duties_industry':dat.isco_title_duties_industry,
    'isco_title_duties':dat.isco_title_duties,
    'isco_code_4d':dat.isco_code_4d
    })

ds_val = Dataset.from_dict({
    'isco_title':val.isco_title,
    'isco_duties':val.isco_duties,
    'isco_title_duties_industry':val.isco_title_duties_industry,
    'isco_title_duties':val.isco_title_duties,
    'isco_code_4d':val.isco_code_4d
    })

#get max token length of titles and duties in order to set emb_model max_length argument\
#this facilitates faster processing speeds as the maximum length per batch is constrained by the\
#max-length argument
from transformers import AutoTokenizer, AutoModel
tokenizer = AutoTokenizer.from_pretrained('model-es/bge-m3')

def get_token_length(batch):
    #get token length in isco_title
    title_len = [len(i)-2 for i in tokenizer(batch['isco_title'])['input_ids']]
    duties_len = [len(i)-2 for i in tokenizer(batch['isco_duties'])['input_ids']]
    title_duties_len = [len(i)-2 for i in tokenizer(batch['isco_title_duties'])['input_ids']]
    title_duties_industry_len = [len(i)-2 for i in tokenizer(batch['isco_title_duties_industry'])['input_ids']]
    return {
        'title_length':title_len,
        'duties_length':duties_len,
        'title_duties_length':title_duties_len,
        'title_duties_industry_length':title_duties_industry_len
    }

temp = ds.map(get_token_length,batched=True)
print('Maximum Title length:')
print(max(temp['title_length']))

print('Maximum Duties length:')
print(max(temp['duties_length']))

print('Maximum Title Duties length:')
print(max(temp['title_duties_length']))

print('Maximum Title Duties Industry length:')
print(max(temp['title_duties_industry_length']))

#load BGE-m3 model
def load_embed_model():
  return BGEM3FlagModel('model-es/bge-m3',use_fp16=False,device='cuda')
emb_model = load_embed_model()

def generate_bge_embedding(batch):
  batch['embeddings_jt']=emb_model.encode(batch['isco_title'],max_length=40)['dense_vecs']
  batch['embeddings_jd']=emb_model.encode(batch['isco_duties'],max_length=128)['dense_vecs']
  batch['embeddings_jtjdind']=emb_model.encode(batch['isco_title_duties_industry'],max_length=150)['dense_vecs']
  batch['embeddings_jtjd']=emb_model.encode(batch['isco_title_duties'],max_length=150)['dense_vecs']
  return batch

ds_ = ds.map(generate_bge_embedding,
       batched=True,
       batch_size=512
       )

#save embedded dataset
ds_.save_to_disk('model-es/datav2/ds_trainv2.hf')

from datasets import load_from_disk
import math
ds_ = load_from_disk('model-es/datav2/ds_train.hf')

# Custom Dataset Class
class CustomDataset(Dataset):
    def __init__(self, labels,
                 custom_embeddings_jt, custom_embeddings_jd, custom_embeddings_jtjd,
                custom_embeddings_jtjdind):
        self.labels = torch.from_numpy(np.array(labels, dtype=np.int64))
        self.custom_embeddings_jt = torch.from_numpy(custom_embeddings_jt)
        self.custom_embeddings_jd = torch.from_numpy(custom_embeddings_jd)
        self.custom_embeddings_jtjd = torch.from_numpy(custom_embeddings_jtjd)
        self.custom_embeddings_jtjdind = torch.from_numpy(custom_embeddings_jtjdind)

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        #title
        custom_embedding_jt = self.custom_embeddings_jt[idx]

        #duties
        custom_embedding_jd = self.custom_embeddings_jd[idx]

        #title/duties
        custom_embedding_jtjd = self.custom_embeddings_jtjd[idx]

        #title + duties + industry
        custom_embedding_jtjdind = self.custom_embeddings_jtjdind[idx]

        # Ensure embeddings have the same shape
        if len(custom_embedding_jt.shape) == 1:
            custom_embedding_jt = custom_embedding_jt.unsqueeze(0)
        if len(custom_embedding_jd.shape) == 1:
            custom_embedding_jd = custom_embedding_jd.unsqueeze(0)
        if len(custom_embedding_jtjd.shape) == 1:
            custom_embedding_jtjd = custom_embedding_jtjd.unsqueeze(0)
        if len(custom_embedding_jtjdind.shape) == 1:
            custom_embedding_jtjdind = custom_embedding_jtjdind.unsqueeze(0)

        #combine job title and job duties embeddings
        custom_embeddings = torch.cat([custom_embedding_jt, custom_embedding_jd],dim=1)
        return {
            'custom_embedding': custom_embeddings, #jt + jd concat
            'custom_embedding_jtjd':custom_embedding_jtjd,
            'custom_embedding_jtjdind':custom_embedding_jtjdind,
            'labels': self.labels[idx]
        }

class BGEModel(nn.Module):
    def __init__(self, custom_embedding_dim, common_dim, drop_out, num_labels):
        super(BGEModel, self).__init__()
        self.custom_embedding_dim = int(custom_embedding_dim) #2048 (vector dimension)
        self.custom_embedding_dim_half = int(custom_embedding_dim/2) #1024
        self.common_dim = int(common_dim) #768
        self.no_labels = num_labels
        self.dropout = drop_out

        #jt + jd
        self.classifier = nn.Sequential(
            nn.Linear(self.custom_embedding_dim, self.custom_embedding_dim_half), #2048 -> 1024
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )
        #jtjd
        self.classifier1 = nn.Sequential(
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )
        #jtjdind
        self.classifier2 = nn.Sequential(
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )

        #combined
        self.classifier_c = nn.Sequential(
            nn.Linear(self.common_dim*3, self.custom_embedding_dim_half), #768*3 -> 1024
            nn.ReLU(),
            nn.Dropout(self.dropout)
         )
        #final layer
        self.fc_out = nn.Linear(self.custom_embedding_dim_half, self.no_labels) #1024 -> 436

    def forward(self, custom_embedding, custom_embedding_jtjd, custom_embedding_jtjdind):

        logits = self.classifier(custom_embedding).to(device)
        logits_jtjd = self.classifier1(custom_embedding_jtjd).to(device)
        logits_jtjdind = self.classifier2(custom_embedding_jtjdind).to(device)

        custom_embedding_c = torch.cat([logits,logits_jtjd,logits_jtjdind],dim=1)

        #pass into interaction layer
        custom_embedding_c = self.classifier_c(custom_embedding_c)
        #pass into classification layer
        logits_out = self.fc_out(custom_embedding_c)
        return logits_out

train = pd.DataFrame(data={
    'labels':ds_['isco_code_4d'],
    'embeddings_jt':ds_['embeddings_jt'],
    'embeddings_jd':ds_['embeddings_jd'],
    'embeddings_jtjd':ds_['embeddings_jtjd'],
    'embeddings_jtjdind':ds_['embeddings_jtjdind']
    })

test = pd.DataFrame(data={
    'labels':ds_val_['isco_code_4d'],
    'embeddings_jt':ds_val_['embeddings_jt'],
    'embeddings_jd':ds_val_['embeddings_jd'],
    'embeddings_jtjd':ds_val_['embeddings_jtjd'],
    'embeddings_jtjdind':ds_val_['embeddings_jtjdind']
    })

#reset index
train.reset_index(inplace=True,drop=True)
test.reset_index(inplace=True,drop=True)

train_dataset = CustomDataset(
                              labels = train.labels.tolist(),
                              custom_embeddings_jt = np.array(train.embeddings_jt.tolist(), dtype=np.float32),
                              custom_embeddings_jd = np.array(train.embeddings_jd.tolist(), dtype=np.float32),
                              custom_embeddings_jtjd = np.array(train.embeddings_jtjd.tolist(), dtype=np.float32),
                              custom_embeddings_jtjdind = np.array(train.embeddings_jtjdind.tolist(), dtype=np.float32)
                              )

train_dataloader = DataLoader(train_dataset, batch_size=128, shuffle=True)

test_dataset = CustomDataset(
    labels = test.labels.tolist(),
    custom_embeddings_jt = np.array(test.embeddings_jt.tolist(), dtype=np.float32),
    custom_embeddings_jd = np.array(test.embeddings_jd.tolist(), dtype=np.float32),
    custom_embeddings_jtjd = np.array(test.embeddings_jtjd.tolist(), dtype=np.float32),
    custom_embeddings_jtjdind = np.array(test.embeddings_jtjdind.tolist(), dtype=np.float32)
)
test_dataloader = DataLoader(test_dataset, batch_size=128, shuffle=True)

# Model Initialization
from transformers import get_linear_schedule_with_warmup
num_labels = len(np.unique(train.labels)) # Number of classes
custom_embedding_dim = 2048
common_dim = 768
dropout_rate = 0.3

# Initialize models
bge_model = BGEModel(custom_embedding_dim, common_dim = common_dim, drop_out = dropout_rate, num_labels=436)
bge_model = bge_model.to('cuda' if torch.cuda.is_available() else 'cpu')

optimizer = torch.optim.AdamW([
    {'params': bge_model.parameters(), 'lr': 1e-3}
    ])

#get counts per class, required for loss function
class_counts = np.bincount(train.labels)

#define loss function
class CB_loss(nn.Module):
    def __init__(self, samples_per_cls, no_of_classes, beta):
        super(CB_loss,self).__init__()
        self.samples_per_cls = samples_per_cls
        self.no_of_classes = no_of_classes
        self.beta = beta

    def forward(self, inputs, target):
        effective_num = 1.0 - np.power(self.beta, self.samples_per_cls)
        weights = (1.0 - self.beta) / np.array(effective_num)
        weights = weights / np.sum(weights) * self.no_of_classes

        labels_one_hot = F.one_hot(target, self.no_of_classes).float()

        weights = torch.tensor(weights).float().to(device)
        weights = weights.unsqueeze(0)
        weights = weights.repeat(labels_one_hot.shape[0],1) * labels_one_hot
        weights = weights.sum(1)
        weights = weights.unsqueeze(1)
        weights = weights.repeat(1,self.no_of_classes)

        pred = inputs.softmax(dim = 1)
        cb_loss = F.binary_cross_entropy(input = pred, target = labels_one_hot, weight = weights) #if using cb loss softmax

        return cb_loss

criterion = CB_loss(samples_per_cls = class_counts, no_of_classes=num_labels,
                   beta=0.999)
num_epoch = 100
num_training_steps = num_epoch * len(train_dataloader)
print(f"Number of training steps: {num_training_steps}")

scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer,mode='max',patience=5, factor=0.8)

best_f1_score = 0
model_sd = dict()
model_sd_list = []

device = 'cuda' if torch.cuda.is_available() else 'cpu'
for epoch in range(num_epoch):  # Number of epochs
    bge_model.train()
    for batch in train_dataloader:
      custom_embedding = batch['custom_embedding'].to(device)
      custom_embedding_jtjd = batch['custom_embedding_jtjd'].to(device)
      custom_embedding_jtjdind = batch['custom_embedding_jtjdind'].to(device)
      labels = batch['labels'].to(device)

      optimizer.zero_grad()
      outputs = bge_model(custom_embedding = custom_embedding,
                           custom_embedding_jtjd = custom_embedding_jtjd,
                           custom_embedding_jtjdind = custom_embedding_jtjdind)

      if len(outputs.shape)==3:
        outputs = outputs.squeeze(1)
      loss = criterion(outputs, labels)
      loss.backward()
      optimizer.step()
      #scheduler.step()
    print(optimizer.param_groups[0]['lr'])
    #check gradients across all parameters
    total_norm = 0
    for param in bge_model.parameters():
        if param.grad is not None:
            param_norm = param.grad.data.norm(2)
            total_norm += param_norm.item()**2
    total_norm = total_norm**0.5
    print(total_norm)

    #model validation
    bge_model.eval()
    val_labels = []
    val_preds = []
    with torch.no_grad():
        for batch in test_dataloader:
          custom_embedding = batch['custom_embedding'].to(device)
          custom_embedding_jtjd = batch['custom_embedding_jtjd'].to(device)
          custom_embedding_jtjdind = batch['custom_embedding_jtjdind'].to(device)

          labels = batch['labels'].to(device)
          outputs = bge_model(custom_embedding = custom_embedding,
                           custom_embedding_jtjd = custom_embedding_jtjd,
                           custom_embedding_jtjdind = custom_embedding_jtjdind)

          if len(outputs.shape)==3:
            outputs = outputs.squeeze(1)

          _, preds = torch.max(outputs, dim=1)
          val_loss = criterion(outputs, labels)
          val_labels.extend(labels.cpu().numpy())
          val_preds.extend(preds.cpu().numpy())

    f1 = f1_score(val_labels, val_preds, average='macro')
    model_sd_list.append(bge_model.state_dict())
    scheduler.step(f1)#NEW
    if (f1>=best_f1_score):
        best_f1_score = f1
        model_sd = deepcopy(bge_model.state_dict())

    print(f"Epoch {epoch+1}, Training Loss: {loss.item()}, Validation Loss: {val_loss.item()} F1 Score: {f1}")

torch.save(model_sd,'model-es/classification bge v5/model.pth')
print(best_f1_score)

#to check if classes that are under-represented in the training set has decent F1-scores
from sklearn.metrics import classification_report
cr = classification_report(val_labels,val_preds,output_dict=True)
u30 = vc_table.loc[vc_table['count']<30]
cr_report = pd.DataFrame(cr).transpose().reset_index()
cr_report.loc[cr_report['index'].isin(list(u30['index'].astype(str)))]

#code below leverages on the python package optuna to optimise the
#hyper-parameters given an objective to minimise/maximise
import optuna
device = 'cuda' if torch.cuda.is_available() else 'cpu'
num_epoch = 120
num_training_steps = num_epoch * len(train_dataloader)

class_counts = np.bincount(train.labels)
class CB_loss(nn.Module):
    def __init__(self, samples_per_cls, no_of_classes, beta):
        super(CB_loss,self).__init__()
        self.samples_per_cls = samples_per_cls
        self.no_of_classes = no_of_classes
        self.beta = beta

    def forward(self, inputs, target):
        effective_num = 1.0 - np.power(self.beta, self.samples_per_cls)
        weights = (1.0 - self.beta) / np.array(effective_num)
        weights = weights / np.sum(weights) * self.no_of_classes

        labels_one_hot = F.one_hot(target, self.no_of_classes).float()

        weights = torch.tensor(weights).float().to(device)
        weights = weights.unsqueeze(0)
        weights = weights.repeat(labels_one_hot.shape[0],1) * labels_one_hot
        weights = weights.sum(1)
        weights = weights.unsqueeze(1)
        weights = weights.repeat(1,self.no_of_classes)
        pred = inputs.softmax(dim = 1)

        cb_loss = F.binary_cross_entropy(input = pred, target = labels_one_hot, weight = weights)
        return cb_loss

def objective(trial):
    #parameters to optimise
    beta = trial.suggest_float("beta",0.1,0.999)
    common_dim = trial.suggest_int("common_dim",64,1024)
    dropout = trial.suggest_float('dropout',0,0.4)

    num_labels = len(np.unique(train.labels)) # Number of classes
    custom_embedding_dim = 2048

    #Initialize model
    bge_model = BGEModel(custom_embedding_dim, common_dim = common_dim, drop_out = dropout, num_labels = 436)
    bge_model = bge_model.to(device)

    optimizer = torch.optim.AdamW([
    {'params': bge_model.parameters(), 'lr': 2e-4}
    ])

    criterion = CB_loss(samples_per_cls = class_counts, no_of_classes=num_labels,
                        beta=beta)
    num_training_steps = num_epoch * len(train_dataloader)

    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=0.2*num_training_steps,
                                             num_training_steps=num_training_steps)

    # Training Loop
    for epoch in range(num_epoch):  # Number of epochs
        bge_model.train()
        for batch in train_dataloader:
          custom_embedding = batch['custom_embedding'].to(device)
          custom_embedding_jtjd = batch['custom_embedding_jtjd'].to(device)
          custom_embedding_jtjdind = batch['custom_embedding_jtjdind'].to(device)
          labels = batch['labels'].to(device)

          optimizer.zero_grad()
          outputs = bge_model(custom_embedding = custom_embedding,
                               custom_embedding_jtjd = custom_embedding_jtjd,
                               custom_embedding_jtjdind = custom_embedding_jtjdind)

          if len(outputs.shape)==3:
            outputs = outputs.squeeze(1)
          loss = criterion(outputs, labels)
          loss.backward()
          optimizer.step()
          scheduler.step()
        #model validation
        bge_model.eval()
        val_labels = []
        val_preds = []
        with torch.no_grad():
            for batch in test_dataloader:
              custom_embedding = batch['custom_embedding'].to(device)
              custom_embedding_jtjd = batch['custom_embedding_jtjd'].to(device)
              custom_embedding_jtjdind = batch['custom_embedding_jtjdind'].to(device)

              labels = batch['labels'].to(device)
              outputs = bge_model(custom_embedding = custom_embedding,
                               custom_embedding_jtjd = custom_embedding_jtjd,
                               custom_embedding_jtjdind = custom_embedding_jtjdind)

              if len(outputs.shape)==3:
                outputs = outputs.squeeze(1)

              _, preds = torch.max(outputs, dim=1)
              val_loss = criterion(outputs, labels)
              val_labels.extend(labels.cpu().numpy())
              val_preds.extend(preds.cpu().numpy())

    f1 = f1_score(val_labels, val_preds, average='macro')
    return f1

#create a study object and optimize the objective function
study = optuna.create_study(direction='maximize')
study.optimize(objective,n_trials=50)

"""Run below for predictions"""

#packages
import torch
from torch import nn
from torch.utils.data import Dataset
import numpy as np
import os
import pandas as pd
import pickle
from sklearn.metrics import f1_score
from FlagEmbedding import BGEM3FlagModel
import torch.nn.functional as F
import os
os.chdir(r'<Specify your directory here>')

class BGEModel(nn.Module):
    def __init__(self, custom_embedding_dim, common_dim, drop_out, num_labels):
        super(BGEModel, self).__init__()
        self.custom_embedding_dim = int(custom_embedding_dim) #2048 (vector dimension)
        self.custom_embedding_dim_half = int(custom_embedding_dim/2) #1024
        self.common_dim = int(common_dim) #768
        self.no_labels = num_labels
        self.dropout = drop_out

        #jt + jd
        self.classifier = nn.Sequential(
            nn.Linear(self.custom_embedding_dim, self.custom_embedding_dim_half), #2048 -> 1024
            nn.ReLU(),
            nn.Dropout(self.dropout),
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )
        #jtjd
        self.classifier1 = nn.Sequential(
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )
        #jtjdind
        self.classifier2 = nn.Sequential(
            nn.Linear(self.custom_embedding_dim_half, self.common_dim), #1024 -> 768
            nn.ReLU(),
            nn.Dropout(self.dropout)
        )

        #combined
        self.classifier_c = nn.Sequential(
            nn.Linear(self.common_dim*3, self.custom_embedding_dim_half), #768*3 -> 1024
            nn.ReLU(),
            nn.Dropout(self.dropout)
         )
        #final layer
        self.fc_out = nn.Linear(self.custom_embedding_dim_half, self.no_labels) #1024 -> 436

    def forward(self, custom_embedding, custom_embedding_jtjd, custom_embedding_jtjdind):

        logits = self.classifier(custom_embedding).to(device)
        logits_jtjd = self.classifier1(custom_embedding_jtjd).to(device)
        logits_jtjdind = self.classifier2(custom_embedding_jtjdind).to(device)

        custom_embedding_c = torch.cat([logits,logits_jtjd,logits_jtjdind],dim=1)

        #pass into interaction layer
        custom_embedding_c = self.classifier_c(custom_embedding_c)
        #pass into classification layer
        logits_out = self.fc_out(custom_embedding_c)
        return logits_out

#construct ds_val_ object from pandas dataset
from datasets import Dataset
df=pd.read_excel('model-es/data/wi_dataset_chatgpt_full.xlsx')
df.fillna('',inplace=True)
#change variable types
df['job_title_norm'] = df['isco_title'].astype(str).str.title()
df['industry_specialisation'] = df['industry_specialisation'].astype(str).str.title()
df['job_duties_abstractive'] = df['description'].astype(str).str.lower()

#create title + duties field
df['isco_title_duties'] = 'job title= ' + df['job_title_norm'] + '| job duties= ' + df['job_duties_abstractive'] #BGE-M3

#title + duties + industry field
df['isco_title_duties_industry'] = 'job title= ' + df['job_title_norm'] + '| job duties= ' + df['job_duties_abstractive'] + \
 '| industry|specialisation= ' + df['industry_specialisation'] #BGE-M3

df.rename(columns={
    'job_title_norm':'isco_title',
    'job_duties_abstractive':'isco_duties',
    'industry_specialisation':'isco_industry'
},inplace=True)
ds=Dataset.from_pandas(df)

df.head()

#load label encoder
le_4d = pickle.load(open('model-es/classification bge v5/labelencoder_4d.pkl','rb'))
device = 'cuda' if torch.cuda.is_available() else 'cpu'
# Model Initialization
#BGE-M3
bge_model = BGEModel(2048, common_dim = 768, drop_out=0.3, num_labels = 436)
bge_model.load_state_dict(torch.load('model-es/classification bge v5/model.pth'))
bge_model.eval()
bge_model = bge_model.to(device)

#load embedding model BGE-M3
def load_embed_model():
  return BGEM3FlagModel('model-es/bge-m3',use_fp16=False,device='cuda')
emb_model = load_embed_model()

from transformers import AutoTokenizer, AutoModel
tokenizer = AutoTokenizer.from_pretrained('model-es/bge-m3')

def get_token_length(batch):
    #get token length in isco_title
    title_len = [len(i)-2 for i in tokenizer(batch['isco_title'])['input_ids']]
    duties_len = [len(i)-2 for i in tokenizer(batch['isco_duties'])['input_ids']]
    title_duties_len = [len(i)-2 for i in tokenizer(batch['isco_title_duties'])['input_ids']]
    title_duties_industry_len = [len(i)-2 for i in tokenizer(batch['isco_title_duties_industry'])['input_ids']]
    return {
        'title_length':title_len,
        'duties_length':duties_len,
        'title_duties_length':title_duties_len,
        'title_duties_industry_length':title_duties_industry_len
    }

ds_ = ds.map(get_token_length,batched=True)

print('Maximum Title length:')
print(max(ds_['title_length']))

print('Maximum Duties length:')
print(max(ds_['duties_length']))

print('Maximum Title Duties length:')
print(max(ds_['title_duties_length']))

print('Maximum Title Duties Industry length:')
print(max(ds_['title_duties_industry_length']))

#reading in ISCO codebook to convert ISCO codes to ISCO code description
isco = pd.read_excel('dictionaries/ISCO-08 EN Structure and definitions.xlsx')
title_dict = isco.loc[isco.Level==4][['ISCO 08 Code','Title EN']]
title_dict['ISCO 08 Code']=title_dict['ISCO 08 Code'].astype(int).astype(str)
title_dict = dict(zip(title_dict['ISCO 08 Code'],title_dict['Title EN']))
vectorized_map = np.vectorize(title_dict.get) #vectorize dictionary

#define helper function to predict by batch using HF datasets
def get_prediction_batch(batch, top_n):
    # Encode the job titles and job duties for all examples in the batch
    custom_embedding_jt = torch.tensor(emb_model.encode(batch['isco_title'], max_length=30)['dense_vecs'],dtype=torch.float).to(device)
    custom_embedding_jd = torch.tensor(emb_model.encode(batch['isco_duties'], max_length=140)['dense_vecs'],dtype=torch.float).to(device)
    custom_embedding_jtjd = torch.tensor(emb_model.encode(batch['isco_title_duties'], max_length=150)['dense_vecs'],dtype=torch.float).to(device)
    custom_embedding_jtjdind = torch.tensor(emb_model.encode(batch['isco_title_duties_industry'], max_length=170)['dense_vecs'],dtype=torch.float).to(device)

    # Ensure custom_embedding has the correct shape
    if len(custom_embedding_jt.shape) == 1:
        custom_embedding_jt = custom_embedding_jt.unsqueeze(0)
    if len(custom_embedding_jd.shape) == 1:
        custom_embedding_jd = custom_embedding_jd.unsqueeze(0)
    if len(custom_embedding_jtjd.shape) == 1:
        custom_embedding_jtjd = custom_embedding_jtjd.unsqueeze(0)
    if len(custom_embedding_jtjdind.shape) == 1:
        custom_embedding_jtjdind = custom_embedding_jtjdind.unsqueeze(0)

    # Concatenate embeddings
    custom_embedding = torch.cat([custom_embedding_jt, custom_embedding_jd], dim=1)

    # Prepare input
    to_predict = {
        'custom_embedding': custom_embedding,
        'custom_embedding_jtjd': custom_embedding_jtjd,
        'custom_embedding_jtjdind':custom_embedding_jtjdind
    }

    m = torch.nn.Softmax(dim=1)
    preds = m(bge_model(**to_predict))
    preds = preds.cpu().detach().numpy()

    # Get top N predictions
    top_n_indices = preds.argsort(axis=1)[:, -top_n:][:, ::-1]  # Indices of top N probabilities
    top_n_probs = np.take_along_axis(preds, top_n_indices, axis=1)

    # Prepare results for the batch
    isco_codes = []
    isco_descs = []
    probabilities = []

    for i in range(preds.shape[0]):
        isco_codes.append(le_4d.inverse_transform(top_n_indices[i].tolist()))
        isco_descs.append(vectorized_map(le_4d.inverse_transform(top_n_indices[i].tolist())))
        probabilities.append(top_n_probs[i].tolist())

    return {
        'isco_code': isco_codes,
        'isco_desc': isco_descs,
        'probabilities': probabilities
    }

#run predict batch function
b=ds.map(get_prediction_batch,batched=True,batch_size=1024,
            fn_kwargs={'top_n':5})

d=b.to_pandas()
d['isco_code'] = [list(i) for i in d['isco_code']] #convert np.array to list
d['isco_desc'] = [list(i) for i in d['isco_desc']]
d['probabilities']=[list(i) for i in d['probabilities']]
d['isco_pred'] = [i[0] for i in d['isco_code']]

#curate classification.csv file
d[['id','isco_pred']].to_csv('model-es/data/classification_161024.csv',index=False)

#save predictions
d.to_excel(r'<Output file path>.xlsx',index=False)