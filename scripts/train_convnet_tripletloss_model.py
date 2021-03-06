"""
This script contains code for a Convolutional Neural Network
that produces an fixed-length continuous-valued vector representation
(embedding) for a 10-second audio clip using a triplet loss function: 
distances in the embedding space will correspond to audio similarity. 
The laughter categories are baby laughter, belly laugh, chuckle/chortle, 
giggle, snicker.

Author: Ganesh Srinivas <gs401 [at] snu.edu.in>
"""

import glob
import os
import random

import tensorflow as tf
import numpy as np

import support_feature_extraction


## Dataset location
FILENAMES = "../dataset/unbalanced/10secondclipfiles.txt"
DATASET_LOCATION = "../dataset/audioset_laughter_clips/"

## Hyperparameters
# for Learning algorithm
learning_rate = 0.01
batch_size = 60 
training_iterations = 10

# for Feature extraction
max_audio_length = 221184
frames = 433
bands = 60
feature_size = frames*bands #433x60

# for Network
num_labels = 5
num_channels = 2 
kernel_size = 30

depth = 20
num_hidden = 200
loss_epsilon = 1e-3

## Helper functions for loading data and extracting features
def labeltext2labelid(category_name):
    """
    Returns a numerical label for each laughter category
    """

    possible_categories = ['baby_laughter_clips', 'belly_laugh_clips', \
    'chuckle_chortle_clips', 'giggle_clips', 'snicker_clips']
    return possible_categories.index(category_name)

def shape_sound_clip(sound_clip, required_length=max_audio_length):
    """
    Shapes sound clips to have constant length
    """
    z=np.zeros((required_length-sound_clip.shape[0],))
    return np.append(sound_clip,z)

def extract_features(filenames):
    """
    Extract log-scaled mel-spectrograms and their corresponding 
    deltas from the sound clips
    """
    log_specgrams = []
    labels=[]

    for f in filenames:
      signal,s = feature_extraction.load(f)
      sound_clip = shape_sound_clip(signal)
      melspec = feature_extraction.melspectrogram(sound_clip, n_mels = 60)

      #print melspec.shape
      logspec = feature_extraction.power_to_db(melspec)
      #print logspec.shape

      logspec = logspec.T.flatten()[:, np.newaxis].T
      #print logspec.shape
      #print "Produce of two elements in melspec: ", melspec.shape[0]*melspec.shape[1]  

      log_specgrams.append(logspec)
      labels.append(labeltext2labelid(f.split('/')[-2]))  

    log_specgrams=np.asarray(log_specgrams).reshape(len(log_specgrams),60,433,1)

    features = np.concatenate((log_specgrams, np.zeros(np.shape(log_specgrams))), axis=3)

    for i in range(len(features)):
          features[i, :, :, 1] = feature_extraction.delta(features[i, :, :, 0])
    return np.array(features), np.array(labels,dtype=np.int)

def one_hot_encode(labels, num_labels=num_labels):
    """
    Convert list of label IDs to a list of one-hot encoding vectors
    """
    n_labels = len(labels)
    n_unique_labels = num_labels

    one_hot_encode = np.zeros((n_labels,n_unique_labels))
    one_hot_encode[np.arange(n_labels), labels] = 1

    return one_hot_encode

## Helper functions for defining the network
def weight_variable(shape):
    initial = tf.truncated_normal(shape, stddev = 0.1)
    return tf.Variable(initial)

def bias_variable(shape):
    initial = tf.constant(1.0, shape = shape)
    return tf.Variable(initial)

def conv2d(x, W):
    return tf.nn.conv2d(x,W,strides=[1,2,2,1], padding='SAME')

def apply_convolution(x,kernel_size,num_channels,depth):
    weights = weight_variable([kernel_size, kernel_size, num_channels, depth])
    biases = bias_variable([depth])

    return tf.nn.relu(tf.add(conv2d(x, weights),biases))

def apply_max_pool(x,kernel_size,stride_size):
    return tf.nn.max_pool(x, ksize=[1, kernel_size, kernel_size, 1], 
                          strides=[1, stride_size, stride_size, 1], padding='SAME')


## Loading the test and train clips.
with open(FILENAMES,"r") as fh:
    filecontents=fh.read()
    filenames=filecontents.split('\n')
    filenames=filenames[:-1] 
    filenames = [DATASET_LOCATION+f for f in filenames]
random.shuffle(filenames)
filenames = filenames[:2250]
#As we are using triplet-loss function, training data must be loaded 
#in a specific manner (not random!): ANCHOR, POSITIVE, NEGATIVE, so on.
rnd_indices = np.random.rand(len(filenames)) < 0.70

print len(rnd_indices)
train = []
test = []

for i in range(len(filenames)):
    if rnd_indices[i]:
        train.append(rnd_indices)
    else:
        test.append(rnd_indices)

print "Train examples: ", len(train)
print "Test examples: ", len(test)

## Defining the network as a TensorFlow computational graph
X = tf.placeholder(tf.float32, shape=[None,bands,frames,num_channels])
Y = tf.placeholder(tf.float32, shape=[None,num_labels])

cov = apply_convolution(X,kernel_size,num_channels,depth)
shape = cov.get_shape().as_list()
cov_flat = tf.reshape(cov, [-1, shape[1] * shape[2] * shape[3]])

f_weights = weight_variable([shape[1] * shape[2] * depth, num_hidden])
f_biases = bias_variable([num_hidden])

f = tf.nn.sigmoid(tf.add(tf.matmul(cov_flat, f_weights),f_biases))
out_weights = weight_variable([num_hidden, num_labels])
out_biases = bias_variable([num_labels])

pred = tf.nn.softmax(tf.matmul(f, out_weights) + out_biases)

# Defining the triplet loss function 
# TODO: Need to replace these Python expressions with TF primitives/calls
#       because I think that not doing so is suboptimal. 
anchor_positive_dist = ((pred[::3] - pred[1::3])**2).sum(axis=1)
anchor_negative_dist = ((pred[::3] - pred[2::3])**2).sum(axis=1)

s = anchor_positive_dist - anchor_negative_dist + loss_epsilon

loss = T.sum(s * tf.greater(s , 0.0))

optimizer = tf.train.AdamOptimizer(learning_rate=learning_rate).minimize(loss)

#train_prediction = tf.nn.softmax(cross_entropy)
correct_prediction = tf.equal(tf.argmax(pred,1), tf.argmax(Y,1))

accuracy = tf.reduce_mean(tf.cast(correct_prediction, tf.float32))

## Running the computational graph
# We run the training algorithm in batches and compute the loss 
# for each batch, and optimize the network weights accordingly.
# In the end, we look at the accuracy of the trained network on the
# test set. 
cost_history = np.empty(shape=[1],dtype=float)
with tf.Session() as session:
    tf.initialize_all_variables().run()

    for itr in range(training_iterations):    
        offset = (itr * batch_size) % (len(train) - batch_size)
        print offset

        batch = filenames[offset:(offset + batch_size)]
        batch_x, batch_y = extract_features(batch)

        batch_y = one_hot_encode(batch_y)
        
        print batch_y.shape, batch_x.shape

        _, c = session.run([optimizer, cross_entropy],feed_dict={X: batch_x, Y : batch_y})
        cost_history = np.append(cost_history,c)

    test_x, test_y = extract_features(test)
    print('Test accuracy: ',round(session.run(accuracy, feed_dict={X: test_x, Y: test_y}) , 3))

    #fig = plt.figure(figsize=(15,10))

    #plt.plot(cost_history)
    #plt.axis([0,training_iterations,0,np.max(cost_history)])
    #plt.show()
