'''
samples from all raw data;
by default samples in a non-iid manner; namely, randomly selects users from 
raw data until their cumulative amount of data exceeds the given number of 
datapoints to sample (specified by --fraction argument);
ordering of original data points is not preserved in sampled data
'''

import argparse
import json
import os
import random
import time

from collections import OrderedDict

from constants import DATASETS, SEED_FILES
from util import iid_divide

parser = argparse.ArgumentParser()

parser.add_argument('--name',
                help='name of dataset to parse; default: sent140;',
                type=str,
                choices=DATASETS,
                default='sent140')
parser.add_argument('--iid',
                help='sample iid;',
                action="store_true")
parser.add_argument('--niid',
                help="sample niid;",
                dest='iid', action='store_false')
parser.add_argument('--union',
                help="sample from union lists;",
                dest='union', action='store_true')
parser.add_argument('--fraction',
                help='fraction of all data to sample; default: 0.1;',
                type=float,
                default=0.1)
parser.add_argument('--u',
                help=('number of users in iid data set; ignored in niid case;'
                      'represented as fraction of original total number of users; '
                      'default: 0.01;'),
                type=float,
                default=0.01)
parser.add_argument('--seed',
                help='seed for random sampling of data',
                type=int,
                default=None)
parser.set_defaults(iid=False)

args = parser.parse_args()

print('------------------------------')
print('sampling data')

parent_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
data_dir = os.path.join(parent_path, args.name, 'data')
subdir = os.path.join(data_dir, 'all_data')
files = os.listdir(subdir)
files = [f for f in files if f.endswith('.json')]

rng_seed = (args.seed if (args.seed is not None and args.seed >= 0) else int(time.time()))
print ("Using seed {}".format(rng_seed))
rng = random.Random(rng_seed)
print (os.environ.get('LEAF_DATA_META_DIR'))
if os.environ.get('LEAF_DATA_META_DIR') is not None:
    seed_fname = os.path.join(os.environ.get('LEAF_DATA_META_DIR'), SEED_FILES['sampling'])
    with open(seed_fname, 'w+') as f:
        f.write("# sampling_seed used by sampling script - supply as "
                "--smplseed to preprocess.sh or --seed to utils/sample.py\n")
        f.write(str(rng_seed))
    print ("- random seed written out to {file}".format(file=seed_fname))
else:
    print ("- using random seed '{seed}' for sampling".format(seed=rng_seed))


if args.union:
    print("=== Sampling users for each union")
    union_dir = os.path.join(data_dir, 'union')
    path_file = os.path.join(union_dir, "union_list_path")

    with open(path_file, "r") as f: 
        union_list_file = f.read()
        os.remove(path_file)

    with open(union_list_file, "r") as f:
        union_list = json.load(f)
    

    total_samples = sum(map(lambda union: sum(map(lambda c: c[1], union)), union_list))
    print("total_samples:", total_samples)

    unions = list(filter(lambda l: len(l) > 1, union_list))
    singles = list(filter(lambda l: len(l) == 1, union_list))
    print("Number of unions:", len(unions))
    print("Number of singles:", len(singles))
    union_num_samples = []
    union_sample = []

    samples_so_far = 0

    for union in unions:
        #print("\tusers:", len(union))
        samples_in_this_union = sum(map(lambda c: c[1], union))
        #print("\tsamples_in_this_union", samples_in_this_union)
        frac = args.fraction * samples_in_this_union
        #print("\tfrac", frac)
        selected_users = []
        sample_count = 0
        for id, samples in union:
            if sample_count + samples > frac:
                break
            selected_users.append(id)
            sample_count += samples
        #print("\tusers in sample:", len(selected_users))
        #print("\tsamples in sample:", sample_count)
        union_sample.append(selected_users)
        union_num_samples.append(sample_count)
        samples_so_far += sample_count


    samples_remain = (total_samples - samples_so_far) * args.fraction
    print("samples remain:", samples_remain)
    
    num_singles = 0

    for single in singles:
        samples_in_this_user = single[0][1]
        id = single[0][0]
        if samples_remain - samples_in_this_user < 0:
            break
        union_sample.append([id])
        union_num_samples.append(samples_in_this_user)
        samples_remain -= samples_in_this_user

        num_singles += 1
        
    union_names = ["union_%d" % i for i in range(len(unions))]
    singles_names = ["single_%d" % i for i in range(num_singles)]
    names = union_names + singles_names

    print("NAMES AND LISTS MATCH:", len(union_sample) == len(names))
    print("number of selected singles:", num_singles, "- total singles: ", len(singles))

    union_data = dict([(name, {"x": [], "y": []}) for name in union_names])    
    for f in files:
        print("Looking for users in",f)
        file_dir = os.path.join(subdir, f)
        with open(file_dir, 'r') as inf:
            data = json.load(inf, object_pairs_hook=OrderedDict)
        for user, user_data in data['user_data'].items():
            for name, union in zip(union_names,union_sample):
                if user in union:
                    union_data[name]['x'] += user_data['x']
                    union_data[name]['y'] += user_data['y']

        #print([(n,len(d["x"])) for n,d in union_data.items()])


    # ------------
    # create .json file

    all_data = {}
    all_data['users'] = union_names
    all_data['num_samples'] = union_num_samples
    all_data['unions'] = union_sample
    all_data['user_data'] = union_data

    slabel = 'union'

    arg_frac = str(args.fraction)
    arg_frac = arg_frac[2:]
    arg_nu = str(args.u)
    arg_nu = arg_nu[2:]
    arg_label = arg_frac
    file_name = '%s_%s.json' % (slabel, arg_label)
    ouf_dir = os.path.join(data_dir, 'sampled_data', file_name)

    # NOTE: For now, we just write everything to one big json. 
    # This will give us issues if we use a large sample.

    print('writing %s' % file_name)
    with open(ouf_dir, 'w') as outfile:
        json.dump(all_data, outfile)

if not args.union:
    new_user_count = 0 # for iid case
    for f in files:
        file_dir = os.path.join(subdir, f)
        with open(file_dir, 'r') as inf:
            # Load data into an OrderedDict, to prevent ordering changes
            # and enable reproducibility
            data = json.load(inf, object_pairs_hook=OrderedDict)

        num_users = len(data['users'])

        tot_num_samples = sum(data['num_samples'])
        num_new_samples = int(args.fraction * tot_num_samples)

        hierarchies = None

        if(args.iid):
            raw_list = list(data['user_data'].values())
            raw_x = [elem['x'] for elem in raw_list]
            raw_y = [elem['y'] for elem in raw_list]
            x_list = [item for sublist in raw_x for item in sublist] # flatten raw_x
            y_list = [item for sublist in raw_y for item in sublist] # flatten raw_y

            num_new_users = int(round(args.u * num_users))
            if num_new_users == 0:
                num_new_users += 1

            indices = [i for i in range(tot_num_samples)]
            new_indices = rng.sample(indices, num_new_samples)
            users = [str(i+new_user_count) for i in range(num_new_users)]

            user_data = {}
            for user in users:
                user_data[user] = {'x': [], 'y': []}
            all_x_samples = [x_list[i] for i in new_indices]
            all_y_samples = [y_list[i] for i in new_indices]
            x_groups = iid_divide(all_x_samples, num_new_users)
            y_groups = iid_divide(all_y_samples, num_new_users)
            for i in range(num_new_users):
                user_data[users[i]]['x'] = x_groups[i]
                user_data[users[i]]['y'] = y_groups[i]
            
            num_samples = [len(user_data[u]['y']) for u in users]

            new_user_count += num_new_users
            
        else:
            ctot_num_samples = 0

            users = data['users']
            users_and_hiers = None
            if 'hierarchies' in data:
                users_and_hiers = list(zip(users, data['hierarchies']))
                rng.shuffle(users_and_hiers)
            else:
                rng.shuffle(users)
            user_i = 0
            num_samples = []
            user_data = {}

            if 'hierarchies' in data:
                hierarchies = []

            while(ctot_num_samples < num_new_samples):
                hierarchy = None
                if users_and_hiers is not None:
                    user, hier = users_and_hiers[user_i]
                else:
                    user = users[user_i]

                cdata = data['user_data'][user]

                cnum_samples = len(data['user_data'][user]['y'])

                if (ctot_num_samples + cnum_samples > num_new_samples):
                    cnum_samples = num_new_samples - ctot_num_samples
                    indices = [i for i in range(cnum_samples)]
                    new_indices = rng.sample(indices, cnum_samples)
                    x = []
                    y = []
                    for i in new_indices:
                        x.append(data['user_data'][user]['x'][i])
                        y.append(data['user_data'][user]['y'][i])
                    cdata = {'x': x, 'y': y}
                
                if 'hierarchies' in data:
                    hierarchies.append(hier)

                num_samples.append(cnum_samples)
                user_data[user] = cdata

                ctot_num_samples += cnum_samples
                user_i += 1

            if 'hierarchies' in data:
                users = [u for u, h in users_and_hiers][:user_i]
            else:
                users = users[:user_i]

        # ------------
        # create .json file

        all_data = {}
        all_data['users'] = users
        if hierarchies is not None:
            all_data['hierarchies'] = hierarchies
        all_data['num_samples'] = num_samples
        all_data['user_data'] = user_data

        slabel = ''
        if(args.iid):
            slabel = 'iid'
        else:
            slabel = 'niid'

        arg_frac = str(args.fraction)
        arg_frac = arg_frac[2:]
        arg_nu = str(args.u)
        arg_nu = arg_nu[2:]
        arg_label = arg_frac
        if(args.iid):
            arg_label = '%s_%s' % (arg_nu, arg_label)
        file_name = '%s_%s_%s.json' % ((f[:-5]), slabel, arg_label)
        ouf_dir = os.path.join(data_dir, 'sampled_data', file_name)

        print('writing %s' % file_name)
        with open(ouf_dir, 'w') as outfile:
            json.dump(all_data, outfile)
