"""
Module containing the encoders.
"""
import numpy as np

import torch
from torch import nn
# import torch.functional as F
import torch.nn.functional as F


# ALL encoders should be called Enccoder<Model>
def get_encoder(model_type):
    model_type = model_type.lower().capitalize()
    return eval("Encoder{}".format(model_type))


class EncoderBurgess(nn.Module):
    def __init__(self, img_size,
                 latent_dim=10):
        r"""Encoder of the model proposed in [1].

        Parameters
        ----------
        img_size : tuple of ints
            Size of images. E.g. (1, 32, 32) or (3, 64, 64).

        latent_dim : int
            Dimensionality of latent output.

        Model Architecture (transposed for decoder)
        ------------
        - 4 convolutional layers (each with 32 channels), (4 x 4 kernel), (stride of 2)
        - 2 fully connected layers (each of 256 units)
        - Latent distribution:
            - 1 fully connected layer of 20 units (log variance and mean for 10 Gaussians)

        References:
            [1] Burgess, Christopher P., et al. "Understanding disentangling in
            $\beta$-VAE." arXiv preprint arXiv:1804.03599 (2018).
        """
        super(EncoderBurgess, self).__init__()

        # Layer parameters
        hid_channels = 32
        kernel_size = 4
        hidden_dim = 256
        self.latent_dim = latent_dim
        self.img_size = img_size
        # Shape required to start transpose convs
        self.reshape = (hid_channels, kernel_size, kernel_size)
        n_chan = self.img_size[0]

        # Convolutional layers
        cnn_kwargs = dict(stride=2, padding=1)
        self.conv1 = nn.Conv2d(n_chan, hid_channels, kernel_size, **cnn_kwargs)
        self.conv2 = nn.Conv2d(hid_channels, hid_channels, kernel_size, **cnn_kwargs)
        self.conv3 = nn.Conv2d(hid_channels, hid_channels, kernel_size, **cnn_kwargs)

        # If input image is 64x64 do fourth convolution
        if self.img_size[1] == self.img_size[2] == 64:
            self.conv_64 = nn.Conv2d(hid_channels, hid_channels, kernel_size, **cnn_kwargs)

        # Fully connected layers
        self.lin1 = nn.Linear(np.product(self.reshape), hidden_dim)
        self.lin2 = nn.Linear(hidden_dim, hidden_dim)

        # Fully connected layers for mean and variance
        self.mu_logvar_gen = nn.Linear(hidden_dim, self.latent_dim * 2)

    def forward(self, x):
        batch_size = x.size(0)

        # Convolutional layers with ReLu activations
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = torch.relu(self.conv3(x))
        if self.img_size[1] == self.img_size[2] == 64:
            x = torch.relu(self.conv_64(x))

        # Fully connected layers with ReLu activations
        x = x.view((batch_size, -1))
        x = torch.relu(self.lin1(x))
        x = torch.relu(self.lin2(x))

        # Fully connected layer for log variance and mean
        # Log std-dev in paper (bear in mind)
        mu_logvar = self.mu_logvar_gen(x)
        mu, logvar = mu_logvar.view(-1, self.latent_dim, 2).unbind(-1)

        return mu, logvar


class ConvEncoder(nn.Module):
    def __init__(self, output_dim):  # latent output dimensions
        super(ConvEncoder, self).__init__()
        self.latent_dim = output_dim
        self.conv1 = nn.Conv2d(3, 64, kernel_size=5, stride=1, padding=2)
        self.bn1 = nn.BatchNorm2d(64)
        self.conv2 = nn.Conv2d(64, 64, kernel_size=5, stride=1, padding=2)
        self.bn2 = nn.BatchNorm2d(64)
        self.conv3 = nn.Conv2d(64, 128, kernel_size=5, stride=1, padding=2)
        self.bn3 = nn.BatchNorm2d(128)
        self.fc1 = nn.Linear(8192, 3072)
        self.bn1_fc = nn.BatchNorm1d(3072)
        self.fc2 = nn.Linear(3072, 2048)
        self.bn2_fc = nn.BatchNorm1d(2048)
        self.mu_logvar_gen = nn.Linear(2048, output_dim * 2)

        # setup the non-linearity
        self.act = nn.LeakyReLU(inplace=True)

    def forward(self, inputs):
        assert len(inputs.shape) == 4
        batch_size, channel, width, height = inputs.size()
        h = inputs.contiguous().view(-1, channel, width, height)
        h = F.max_pool2d(self.act(self.bn1(self.conv1(h))),  stride=2, kernel_size=3, padding=1)
        h = F.max_pool2d(self.act(self.bn2(self.conv2(h))), stride=2, kernel_size=3, padding=1)
        h = self.act(self.bn3(self.conv3(h)))
        # [CHECK] did not add dropout so far
        h = h.view(batch_size, -1)
        h = self.act(self.bn1_fc(self.fc1(h)))
        h = self.act(self.bn2_fc(self.fc2(h)))
        mu_logvar = self.mu_logvar_gen(h)

        outputs = mu_logvar.view(batch_size, self.latent_dim, 2).unbind(-1)

        return outputs



class DomainEncoder(nn.Module):
    def __init__(self, num_domains, output_dim):
        super(DomainEncoder, self).__init__()
        self.latent_dim = output_dim
        self.embed = nn.Embedding(num_domains, 512)
        self.bn = nn.BatchNorm1d(512)
        self.mu_logvar_gen = nn.Linear(512, output_dim * 2)

        # setup the non-linearity
        self.act = nn.LeakyReLU(inplace=True)

    def forward(self, inputs):
        batch_size = inputs.size()[0]
        # inputs.cuda()
        h = self.act(self.bn(self.embed(inputs)))
        mu_logvar = self.mu_logvar_gen(h)
        outputs = mu_logvar.view(batch_size, self.latent_dim, 2).unbind(-1)

        return outputs