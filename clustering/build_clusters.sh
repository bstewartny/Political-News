export JAVA_HOME=/usr

rm vectors.vec
rm dict.out
rm -R kmeans
rm -R canopy

mkdir canopy
mkdir kmeans
mkdir kmeans/clusters
rm output

# build vectors from lucene index
/usr/local/mahout/bin/mahout lucene.vector --dir /var/data/solr_pol/index --output vectors.vec --minDF 2 --maxDFPercent 40 --field text --idField title --dictOut dict.out

# capopy clusters
/usr/local/mahout/bin/mahout canopy

# apply k-means clustering to vectors
/usr/local/mahout/bin/mahout kmeans --distanceMeasure org.apache.mahout.common.distance.CosineDistanceMeasure -cd 0.01 --input vectors.vec --clustering --clusters kmeans/clusters --maxIter 80 --output kmeans --numClusters 40 --overwrite

# dump cluster output
#/usr/local/mahout/bin/mahout clusterdump -s kmeans/clusters-2-final -p kmeans/clusteredPoints -d dict.out -o output

