import argparse
import os.path as osp
import os
import sys
from datetime import datetime
import json

import numpy as np


import torch

from torch.utils.data import Subset

sys.path.append(os.getcwd())
import defenses.config as cfg
from defenses import datasets
import defenses.models.zoo as zoo
import defenses.utils.admis as model_utils_admis



def main():
    parser = argparse.ArgumentParser(description='Train a model')
    # Required arguments
    parser.add_argument('dataset', metavar='DS_NAME', type=str, help='Dataset name')
    parser.add_argument('model_arch', metavar='MODEL_ARCH', type=str, help='Model name')
    # Optional arguments
    parser.add_argument('-o', '--out_path', metavar='PATH', type=str, help='Output path for model',
                        default=cfg.MODEL_DIR)
    parser.add_argument('-d', '--device_id', metavar='D', type=int, help='Device id. -1 for CPU.', default=0)
    parser.add_argument('-b', '--batch_size', type=int, default=32, metavar='N',
                        help='input batch size for training (default: 64)')
    parser.add_argument('-e', '--epochs', type=int, default=100, metavar='N',
                        help='number of epochs to train (default: 100)')
    parser.add_argument('--lr', type=float, default=0.1, metavar='LR',
                        help='learning rate (default: 0.1)')
    parser.add_argument('--momentum', type=float, default=0.5, metavar='M',
                        help='SGD momentum (default: 0.5)')
    parser.add_argument('--log_interval', type=int, default=50, metavar='N',
                        help='how many batches to wait before logging training status')
    parser.add_argument('--resume', default=None, type=str, metavar='PATH',
                        help='path to latest checkpoint (default: none)')
    parser.add_argument('--lr_step', type=int, default=50, metavar='N',
                        help='Step sizes for LR')
    parser.add_argument('--lr_gamma', type=float, default=0.1, metavar='N',
                        help='LR Decay Rate')
    parser.add_argument('-w', '--num_workers', metavar='N', type=int, help='# Worker threads to load data', default=10)
    parser.add_argument('--train_subset', type=int, help='Use a subset of train set', default=None)
    parser.add_argument('--pretrained', type=str, help='Use pretrained network', default=None)
    parser.add_argument('--weighted_loss', action='store_true', help='Use a weighted loss', default=None)

    # Args for Adaptive Misinformation with Outlier Exposure
    parser.add_argument('--oe_lamb', type=float, default=0.0, metavar='LAMB',
                        help='Lambda for Outlier Exposure')
    parser.add_argument('-doe', '--dataset_oe', metavar='DS_OE_NAME', type=str, help='OE Dataset name',
                        default='Indoor67')
    
    args = parser.parse_args()
    params = vars(args)

    # Set device
    if params['device_id'] >= 0:
        os.environ["CUDA_VISIBLE_DEVICES"] = str(params['device_id'])
        device = torch.device('cuda')
    else:
        device = torch.device('cpu')

    # ----------- Set up dataset
    # in-distribution dataset
    dataset_name = params['dataset']
    valid_datasets = datasets.__dict__.keys()
    if dataset_name not in valid_datasets:
        raise ValueError('Dataset not found. Valid arguments = {}'.format(valid_datasets))
    dataset = datasets.__dict__[dataset_name]

    modelfamily = datasets.dataset_to_modelfamily[dataset_name]
    train_transform = datasets.modelfamily_to_transforms[modelfamily]['train']
    test_transform = datasets.modelfamily_to_transforms[modelfamily]['test']
    trainset = dataset(train=True, transform=train_transform,download=True)
    testset = dataset(train=False, transform=test_transform,download=True)
    num_classes = len(trainset.classes)
    params['num_classes'] = num_classes

    if params['train_subset'] is not None:
        idxs = np.arange(len(trainset))
        ntrainsubset = params['train_subset']
        idxs = np.random.choice(idxs, size=ntrainsubset, replace=False)
        trainset = Subset(trainset, idxs)

    # out-distribution dataset
    dataset_oe_name = params['dataset_oe']
    if dataset_oe_name not in valid_datasets:
        raise ValueError('OE Dataset not found. Valid arguments = {}'.format(valid_datasets))
    dataset_oe = datasets.__dict__[dataset_oe_name]

    modelfamily_oe = datasets.dataset_to_modelfamily[dataset_oe_name]
    train_oe_transform = datasets.modelfamily_to_transforms[modelfamily_oe]['train']
    test_oe_transform = datasets.modelfamily_to_transforms[modelfamily_oe]['test']
    trainset_oe = dataset_oe(train=True, transform=train_oe_transform,download=True)
    testset_oe = dataset_oe(train=False, transform=test_oe_transform,download=True)


    # ----------- Set up model
    model_name = params['model_arch']
    pretrained = params['pretrained']
    model = zoo.get_net(model_name, modelfamily, pretrained, num_classes=num_classes)
    model = model.to(device)

    # misinforamtion model
    model_poison = zoo.get_net(model_name, modelfamily, pretrained,
                                num_classes=num_classes)  # Alt model for Selective Misinformation
    model_poison = model_poison.to(device)

    # ----------- Train
    out_path = params['out_path']
    model_utils_admis.train_model(model, trainset=trainset, trainset_OE=trainset_oe, testset=testset, testset_OE=testset_oe,
                        model_poison=model_poison, device=device, **params)
    
    torch.save(model_poison.state_dict(), out_path + '/model_poison.pt')
    
    # Store arguments
    params['created_on'] = str(datetime.now())
    params_out_path = osp.join(out_path, 'params.json')
    with open(params_out_path, 'w') as jf:
        json.dump(params, jf, indent=True)

if __name__ == '__main__':
    main()

