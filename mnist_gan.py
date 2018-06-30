import tensorflow as tf 
import numpy as np
import argparse
import helper
import os
from glob import glob
from shutil import rmtree

class MnistGAN():

    def __init__(self):
        pass 

    def show_generator_output(self, sess, n_images, input_z, out_channel_dim, image_mode):
        """
        Show example output for the generator
        :param sess: TensorFlow session
        :param n_images: Number of Images to display
        :param input_z: Input Z Tensor
        :param out_channel_dim: The number of channels in the output image
        :param image_mode: The mode to use for images ("RGB" or "L")
        """
        z_dim = input_z.get_shape().as_list()[-1]
        example_z = np.random.uniform(-1, 1, size=[n_images, z_dim])

        samples = sess.run(
            self.generator(input_z, out_channel_dim, False),
            feed_dict={input_z: example_z})

        return np.array(helper.images_square_grid(samples, image_mode))

    def model_loss(self, input_real, input_z, out_channel_dim):
        """
        Get the loss for the discriminator and generator
        :param input_real: Images from the real dataset
        :param input_z: Z input
        :param out_channel_dim: The number of channels in the output image
        :return: A tuple of (discriminator loss, generator loss)
        """

        g_model = self.generator(input_z, out_channel_dim)
        d_model_real, d_logits_real = self.discriminator(input_real)
        d_model_fake, d_logits_fake = self.discriminator(g_model, reuse = True)
        
        d_loss_real = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits = d_logits_real, 
                                                    labels=0.9*tf.ones_like(d_model_real)))
        
        d_loss_fake = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits = d_logits_fake, 
                                                    labels=tf.zeros_like(d_model_fake)))
        
        g_loss = tf.reduce_mean(
            tf.nn.sigmoid_cross_entropy_with_logits(logits = d_logits_fake, 
                                                    labels=tf.ones_like(d_model_fake)))
        
        d_loss = d_loss_real + d_loss_fake
        
        return d_loss, g_loss

    def model_inputs(self, image_width, image_height, image_channels, z_dim):
        """
        Create the model inputs
        :param image_width: The input image width
        :param image_height: The input image height
        :param image_channels: The number of image channels
        :param z_dim: The dimension of Z
        :return: Tuple of (tensor of real input images, tensor of z data, learning rate)
        """
        inputs_real = tf.placeholder(tf.float32, 
                                    shape=(None, image_width, image_height, image_channels), 
                                    name='inputs_real')

        inputs_z = tf.placeholder(tf.float32, 
                                shape=(None, z_dim), 
                                name='inputs_z')

        learning_rate = tf.placeholder(tf.float32)

        return inputs_real, inputs_z, learning_rate

    def generator(self, z, out_channel_dim, is_train=True):
        """
        Create the generator network
        :param z: Input z
        :param out_channel_dim: The number of channels in the output image
        :param is_train: Boolean if generator is being used for training
        :return: The tensor output of the generator
        """
    
        alpha = 0.2 # Leaky ReLu hyperparameter
        with tf.variable_scope('generator', reuse = not is_train):
            # output shape should be 28 x 28 x out_channel_dim
            
            # dense layer + reshape 
            # output shape: (-1,7,7,64)
            x = tf.layers.dense(z, units=7*7*64, activation=None)
            x = tf.reshape(x, shape=[-1,7,7,64])
            x = tf.layers.batch_normalization(x,training = is_train) 
            x = tf.maximum(alpha * x, x) # Leaky ReLu
            
            # transpose convolution layer #1
            # output shape: (-1,14,14,128)
            x1 = tf.layers.conv2d_transpose(x,filters=128,kernel_size=5,strides=2, padding='same')
            x1 = tf.layers.batch_normalization(x1,training = is_train)
            x1 = tf.maximum(alpha * x1, x1) # Leaky ReLu
            
            # transpose convolution layer #2
            # output shape, (-1,28,28,output_dim)
            logits = tf.layers.conv2d_transpose(x1,filters=out_channel_dim,kernel_size=5,strides=2, padding='same')
            out = tf.tanh(logits)

            return out

    def discriminator(self, images, reuse=False):
        """
        Create the discriminator network
        :param images: Tensor of input image(s)
        :param reuse: Boolean if the weights should be reused
        :return: Tuple of (tensor output of the discriminator, tensor logits of the discriminator)
        """

        alpha = 0.2 # Leaky ReLu hyperparameter
        with tf.variable_scope('discriminator', reuse = reuse):
            # images shape: (-1, 28, 28, out_channel_dim)
        
            # convolutional layer #1
            # output shape: (-1, 14, 14, 64)
            # no batch normalization for the first layer
            x1 = tf.layers.conv2d(images, filters=64, kernel_size=5, strides=2, padding='same')
            x1 = tf.maximum(alpha * x1, x1) # Leaky ReLu
        
            # convolutional layer #2
            # output shape: (-1, 7, 7, 128)
            # batch normalization
            x2 = tf.layers.conv2d(x1, filters=128, kernel_size=5, strides=2, padding='same')
            x2 = tf.layers.batch_normalization(x2,training=True) 
            x2 = tf.maximum(alpha * x2, x2) # Leaky ReLu
        
            # reshape
            # output shape: (-1,4*4*64)
            x2_reshape = tf.reshape(x2,shape=[-1,7*7*128])
        
            # output layer
            # output shape: (-1,1)
            logits = tf.layers.dense(x2_reshape, units=1, activation=None)
            out = tf.sigmoid(logits)
        
            return out, logits

    def model_opt(self, d_loss, g_loss, learning_rate, beta1):
        """
        Get optimization operations
        :param d_loss: Discriminator loss Tensor
        :param g_loss: Generator loss Tensor
        :param learning_rate: Learning Rate Placeholder
        :param beta1: The exponential decay rate for the 1st moment in the optimizer
        :return: A tuple of (discriminator training operation, generator training operation)
        """
    
        t_vars = tf.trainable_variables()
        d_vars = [var for var in t_vars if var.name.startswith('discriminator')]
        g_vars = [var for var in t_vars if var.name.startswith('generator')]
        
        with tf.control_dependencies(tf.get_collection(tf.GraphKeys.UPDATE_OPS)):
            d_train_opt = tf.train.AdamOptimizer(learning_rate, beta1=beta1).minimize(d_loss, var_list=d_vars)
            g_train_opt = tf.train.AdamOptimizer(learning_rate, beta1=beta1).minimize(g_loss, var_list=g_vars)

        return d_train_opt, g_train_opt

    def train(self, epoch_count, batch_size, z_dim, learning_rate, beta1, get_batches, data_shape, data_image_mode, 
              loss_each, 
              image_each, 
              log_dir):
        """
        Train the GAN
        :param epoch_count: Number of epochs
        :param batch_size: Batch Size
        :param z_dim: Z dimension
        :param learning_rate: Learning Rate
        :param beta1: The exponential decay rate for the 1st moment in the optimizer
        :param get_batches: Function to get batches
        :param data_shape: Shape of the data
        :param data_image_mode: The image mode to use for images ("RGB" or "L")
        """

        image_channels = 1
        if data_image_mode == 'RGB':
            image_channels = 3
        
        inputs_real, inputs_z, lr = self.model_inputs(data_shape[1], data_shape[2], image_channels, z_dim)
        d_loss, g_loss = self.model_loss(inputs_real, inputs_z, image_channels)
        d_opt, g_opt = self.model_opt(d_loss, g_loss, learning_rate, beta1)

        # placeholder for images summary
        train_images = tf.placeholder(tf.float32, shape=[None, data_shape[1], data_shape[2], image_channels])

        # tensorboard summaries 
        disc_summ = tf.summary.scalar('discriminator loss', d_loss)
        gen_summ = tf.summary.scalar('generator loss', g_loss)
        summ_images = tf.summary.image('train images', train_images, 1)
        summ = tf.summary.merge([disc_summ, gen_summ])
        
        it = 0
        with tf.Session() as sess:
            sess.run(tf.global_variables_initializer())
            writer = self._create_writer(log_dir, sess) 
            for epoch_i in range(epoch_count):
                print("Running epoch {}/{}...".format(epoch_i+1, epoch_count) )
                for batch_images in get_batches(batch_size):

                    batch_z = np.random.uniform(-1, 1, size=(batch_size, z_dim))
                    
                    _ = sess.run(d_opt, feed_dict={inputs_real: batch_images*2, inputs_z: batch_z, lr: learning_rate})
                    _ = sess.run(g_opt, feed_dict={inputs_z: batch_z, inputs_real: batch_images*2, lr: learning_rate})
                    
                    if it % loss_each == 0:
                        # log summaries to tensorboard
                        s = sess.run(summ, feed_dict={inputs_real: batch_images*2, inputs_z: batch_z}) 
                        writer.add_summary(s, it)

                    if it % image_each == 0:
                        # log images to tensorboard
                        img_arr = self.show_generator_output(sess, 1, inputs_z, image_channels, data_image_mode)
                        img_arr_reshape = np.reshape(img_arr, (1, 28,28,image_channels ))
                        s = sess.run(summ_images, feed_dict={train_images: img_arr_reshape})
                        writer.add_summary(s, it)
                    
                    it+=1
            
            print('Done.')

    # Helpers

    def _create_writer(self, path, sess):
        """
        - Check if folder exits if not creates it and create summary writer with specified name
        """
        if os.path.exists(path):
            rmtree(path)
        os.makedirs(path)
        writer = tf.summary.FileWriter(path, sess.graph)
        return writer

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description = 'MNIST GAN')  
    parser.add_argument("--train", "-t", help="to train mode", action='store_true')
    parser.add_argument('--epochs', help='set number of epochs (default=2)', default=2)
    parser.add_argument('--batch_size', help='set batch size (default=32)', default=32)
    parser.add_argument('--z_dim', help='set z dim (default=100)', default=100)
    parser.add_argument('--lrate', help='set learning rate (default=0.0004)', default=0.0004)
    parser.add_argument('--beta1', help='set adam optimizer beta_1 (default=0.7)', default=0.6)
    parser.add_argument('--loss_each', help='log loss to tensorboard each (default=10)', default=10 )
    parser.add_argument('--image_each', help='log image to tensorboard each (default=100)', default=100 )
    parser.add_argument('--log_dir', help='set tensorboard log dir (default=log/mnist)', default='log/mnist')

    args = parser.parse_args()

    if args.train:
        # run train 

        # create GAN 
        gan = MnistGAN()

        # get data
        mnist_dataset = helper.Dataset('mnist', glob('data/mnist/*.jpg'))

        gan.train(args.epochs,
                  args.batch_size,
                  args.z_dim,
                  args.lrate, 
                  args.beta1,
                  mnist_dataset.get_batches,
                  mnist_dataset.shape,
                  mnist_dataset.image_mode,
                  args.loss_each, 
                  args.image_each,
                  args.log_dir)

# to train with default values
# python mnist_gan.py --train 

# tensorboard --logdir=log/mnist

# floyd run --cpu --tensorboard --data mckay/datasets/mnist/1:data/mnist "python mnist_gan.py --train --log_dir output/log"