# -*- coding: utf-8 -*-
import pandas as pd
import json
import utils
data1 = {'变量111':230,'变量2':29}
data2 = {'变量25':21,'变量129':90}
data3 = {'变量211':215,'变量67':30}

df = pd.DataFrame()
df = df.append(data1,ignore_index=True)
df = df.append(data2,ignore_index=True) #合并并且列智能连接
print(df.columns.values.tolist())
#df.drop(df.index, inplace=True) #清空


#df.to_csv('./2000-01-01.csv',mode='a',header=False) #但是不能智能连接
#print(df)