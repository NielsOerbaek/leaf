"""Script to run the baselines."""
import argparse
import importlib
import numpy as np
import os
import sys
import random
import tensorflow as tf

import metrics.writer as metrics_writer

from baseline_constants import MAIN_PARAMS, MODEL_PARAMS
from client import Client
from server import Server
from model import ServerModel

from utils.args import parse_args
from utils.model_utils import read_data

STAT_METRICS_PATH = 'metrics/stat_metrics.csv'
SYS_METRICS_PATH = 'metrics/sys_metrics.csv'

def main():

    args = parse_args()

    # Set the random seed if provided (affects client sampling, and batching)
    random.seed(1 + args.seed)
    np.random.seed(12 + args.seed)
    tf.set_random_seed(123 + args.seed)

    model_path = '%s/%s.py' % (args.dataset, args.model)
    if not os.path.exists(model_path):
        print('Please specify a valid dataset and a valid model.')
    model_path = '%s.%s' % (args.dataset, args.model)
    
    print('############################## %s ##############################' % model_path, flush=True)
    mod = importlib.import_module(model_path)
    ClientModel = getattr(mod, 'ClientModel')

    tup = MAIN_PARAMS[args.dataset][args.t]
    num_rounds = args.num_rounds if args.num_rounds != -1 else tup[0]
    eval_every = args.eval_every if args.eval_every != -1 else tup[1]
    clients_per_round = args.clients_per_round if args.clients_per_round != -1 else tup[2]

    # Suppress tf warnings
    tf.logging.set_verbosity(tf.logging.WARN)

    # Create 2 models
    model_params = MODEL_PARAMS[model_path]
    if args.lr != -1:
        model_params_list = list(model_params)
        model_params_list[0] = args.lr
        model_params = tuple(model_params_list)

    # Create client model, and share params with server model
    tf.reset_default_graph()
    client_model = ClientModel(args.seed, *model_params)

    # Create server
    server = Server(client_model)

    # Create clients
    clients = setup_clients(args.dataset, client_model, args.use_val_set)
    client_ids, client_groups, client_num_samples, client_num_users = server.get_clients_info(clients)
    print('Clients in Total: %d' % len(clients))
    print('Maximum number of users in a client (largest union): %d' % max([c.num_users for c in clients]))

    # Initial status
    print('--- Random Initialization ---', flush=True)
    stat_writer_fn = get_stat_writer_function(client_ids, client_groups, client_num_samples, args)
    sys_writer_fn = get_sys_writer_function(args)
    print_stats(0, server, clients, client_num_samples, args, stat_writer_fn, args.use_val_set, client_num_users)

    # State for the early stopping target
    round_where_target_reached = None
    final_rounds = 50

    # Simulate training
    for i in range(num_rounds):
        print('--- Round %d of %d: Training %d Clients ---' % (i + 1, num_rounds, clients_per_round), flush=True)

        # Select clients to train this round
        server.select_clients(i, online(clients), num_clients=clients_per_round)
        c_ids, c_groups, c_num_samples, c_num_users = server.get_clients_info(server.selected_clients)

        # Simulate server model training on selected clients' data
        sys_metrics = server.train_model(num_epochs=args.num_epochs, batch_size=args.batch_size, minibatch=args.minibatch)
        sys_writer_fn(i + 1, c_ids, sys_metrics, c_groups, c_num_samples, c_num_users)
        
        # Update server model
        server.update_model()

        # Test model
        if (i + 1) % eval_every == 0 or (i + 1) == num_rounds:
            #Note: We use the number of users as the weight
            metrics = print_stats(i + 1, server, clients, client_num_samples, args, stat_writer_fn, args.use_val_set, client_num_users)
            
            if args.target_performance:
                if round_where_target_reached: 
                    print(f"\t!!!!q Only {final_rounds - (i+1 - round_where_target_reached)} rounds left till we quit")
                    if (i+1 - round_where_target_reached) >= final_rounds:
                        print("Goodbye!")
                        exit()
                else:
                    ordered_metric = [metrics[c][args.target_metric] for c in sorted(metrics)]
                    ordered_weights = [client_num_users[c] for c in sorted(client_num_users)]
                    performance = np.average(ordered_metric, weights=ordered_weights)

                    print("Current Performance: %.2f - Target %.2f - Remaining: %.2f" % (performance, args.target_performance, args.target_performance - performance))
                    if performance >= args.target_performance:
                        print("Reached target performance, will run %d final rounds and then quit." % final_rounds)
                        round_where_target_reached = i+1
            
    # Save server model
    ckpt_path = os.path.join('checkpoints', args.dataset)
    if not os.path.exists(ckpt_path):
        os.makedirs(ckpt_path)
    save_path = server.save_model(os.path.join(ckpt_path, '{}.ckpt'.format(args.model)))
    print('Model saved in path: %s' % save_path, flush=True)

    # Close models
    server.close_model()

def online(clients):
    """We assume all users are always online."""
    return clients


def create_clients(users, groups, unions, train_data, test_data, model):
    if len(groups) == 0:
        groups = [[] for _ in users]
    if len(unions) == 0:
        unions = [[] for _ in users]

    clients = [Client(us, g, un, train_data[us], test_data[us], model) for us, g, un in zip(users, groups, unions)]
    return clients


def setup_clients(dataset, model=None, use_val_set=False):
    """Instantiates clients based on given train and test data directories.

    Return:
        all_clients: list of Client objects.
    """
    eval_set = 'test' if not use_val_set else 'val'
    train_data_dir = os.path.join('..', 'data', dataset, 'data', 'train')
    test_data_dir = os.path.join('..', 'data', dataset, 'data', eval_set)

    users, groups, unions, train_data, test_data = read_data(train_data_dir, test_data_dir)

    clients = create_clients(users, groups, unions, train_data, test_data, model)

    return clients


def get_stat_writer_function(ids, groups, num_samples, args):

    def writer_fn(num_round, metrics, partition, num_users):
        metrics_writer.print_metrics(
                num_round, ids, metrics, groups, num_samples, partition, num_users, args.metrics_dir, '{}_{}'.format('stat',args.metrics_name)) #NOTE: You switched around the arguments in the file name so it matches the rest of the files

    return writer_fn


def get_sys_writer_function(args):

    def writer_fn(num_round, ids, metrics, groups, num_samples, num_users):
        metrics_writer.print_metrics(
            num_round, ids, metrics, groups, num_samples, 'train', num_users, args.metrics_dir, '{}_{}'.format('sys',args.metrics_name)) #NOTE: You switched around the arguments in the file name so it matches the rest of the files

    return writer_fn


def print_stats(
    num_round, server, clients, client_num_samples, args, writer, use_val_set, client_num_users):
    
    weights = client_num_users if client_num_users else client_num_samples

    train_stat_metrics = server.test_model(clients, set_to_use='train')
    print_metrics(train_stat_metrics, weights, prefix='train_')
    writer(num_round, train_stat_metrics, 'train', client_num_users)

    eval_set = 'test' if not use_val_set else 'val'
    test_stat_metrics = server.test_model(clients, set_to_use=eval_set)
    print_metrics(test_stat_metrics, weights, prefix='{}_'.format(eval_set))
    writer(num_round, test_stat_metrics, eval_set, client_num_users)

    return test_stat_metrics    


def print_metrics(metrics, weights, prefix=''):
    """Prints weighted averages of the given metrics.

    Args:
        metrics: dict with client ids as keys. Each entry is a dict
            with the metrics of that client.
        weights: dict with client ids as keys. Each entry is the weight
            for that client.
    """
    ordered_weights = [weights[c] for c in sorted(weights)]
    metric_names = metrics_writer.get_metrics_names(metrics)
    to_ret = None
    for metric in metric_names:
        ordered_metric = [metrics[c][metric] for c in sorted(metrics)]
        print('%s: %g, 10th percentile: %g, 50th percentile: %g, 90th percentile %g' \
              % (prefix + metric,
                 np.average(ordered_metric, weights=ordered_weights), # NOTE: You are now weighting pr user and not pr sample
                 np.percentile(ordered_metric, 10),
                 np.percentile(ordered_metric, 50),
                 np.percentile(ordered_metric, 90)), flush=True)


if __name__ == '__main__':
    main()
