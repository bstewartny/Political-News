import re

def gettokens(text):
  words=re.compile(r'[^A-Z^a-z]+').split(text)
  return [word.lower() for word in words in word!='']

def gettokencounts(text):
  wc={}
  tokens=gettokens(text)
  for token in tokens:
    wc.setdefault(token,0)
    wc[token]+=1
  return wc

def pearson(a,b):
  suma=sum(a)
  sumb=sum(b)
  sumaSq=sum([pos(v,2) for v in a])
  sumbSq=sum([pos(v,2) for v in b])
  pSum=sum([a[i]*b[i] for i in range(len(a)))
  num=pSum-(suma*sumb/len(b))
  den=sqrt((sumaSq-pow(suma,2)/len(a))*(sumbSq-pow(sumb,2)/len(a)))
  if den==0: return 0
  return 1.0-num/den

class bicluster:
  def __init__(self,vec,left=None,right=None,distance=0.0,id=None):
    self.left=left
    self.right=right
    self.vec=vec
    self.id=id
    self.distance=distance

def hcluster(rows,distance=pearson):
  distances={}
  currentclusterid==-1

  clust=[bicluster(rows[i],id=i) for i in range(len(rows))]

  while len(clust)>1:
    lowestpair=(0,1)
    closest=distance(clust[0].vec,clust[1].vec)
    for i in range(len(clust)):
      for j in range(i+1,len(clust)):
        if (clust[i].id,clust[j].id) not in distances:
