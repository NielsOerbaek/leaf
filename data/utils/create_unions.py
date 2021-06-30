# Takes a large json file of users and their data and creates unions

from __future__ import division
import json
import math
import numpy as np
import os
import sys
import argparse
from tqdm import tqdm

from constants import DATASETS, SEED_FILES

parser = argparse.ArgumentParser()

parser.add_argument('--name',
                help='name of dataset to parse; default: sent140;',
                type=str,
                choices=DATASETS,
                default='uni-femnist')
parser.add_argument('--size',
                help='fraction of users in each equally sized union',
                type=float,
                default='0.05')
parser.add_argument('-f',
                help='force extract of user info',
                action="store_true")

args = parser.parse_args()

parent_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
data_dir = os.path.join(parent_path, args.name, 'data')
subdir = os.path.join(data_dir, 'all_data')
union_dir = os.path.join(data_dir, 'union')
files = os.listdir(subdir)
files = [f for f in files if f.endswith('.json')]

def get_users():
    if not os.path.exists(union_dir):
        os.mkdir(union_dir)

    users = {'users': [], 'num_samples': []}

    #Extract_data
    for file in tqdm(files):
        data = json.load(open(os.path.join(subdir, file),"r"))
        users["users"] += data["users"]
        users["num_samples"] += data["num_samples"]
    
    outfile = os.path.join(union_dir, "user_info.json")
    json.dump(users, open(outfile,"w"))
    
    return users
    

def equal_unions(users, union_size=0.05):
    # Returns a list of (1/num_union) lists with user_ids

    shuffle_seed = 9873248
    np.random.seed(shuffle_seed)

    num_unions = math.ceil(1/union_size)
    
    ids = np.array(users["users"])
    np.random.shuffle(ids)

    unions = [[] for _ in range(num_unions)]

    for i,u in enumerate(ids):
        unions[i%num_unions].append(u)

    return unions


def single_union(users, union_size=0.1):
    # Returns a list of user_id lists, where one of them is a union of size (len(users)*union_size)

    shuffle_seed = 9873248
    np.random.seed(shuffle_seed)

    ids = np.array(users["users"])
    np.random.shuffle(ids)

    union_size = math.ceil(len(users)*union_size)

    print(len(ids))
    print(union_size)

    num_lists = len(ids)-union_size+1

    unions = [[] for _ in range(num_lists)]

    unions[0] = ids[:union_size]

    for user in ids[union_size:]:
        unions.append([user])

    print(unions)

    return unions


def create_union_lists(users, union_type="equal", union_size=0.05):
    if union_type == "equal":
        unions = equal_unions(users,union_size)

    if union_type == "single":
        unions = single_union(users,union_size)

    num_samples = list(map(int, users["num_samples"]))
    sample_dict = dict(zip(users["users"],num_samples))

    union_tuples = []

    for u in unions:
        ut = list(map(lambda id: (id, sample_dict[id]), u))
        union_tuples.append(ut)
    
    filename = "union_lists_%s_%s.json" % (union_type, union_size)
    path = os.path.join(union_dir, filename)
    json.dump(union_tuples, open(path,"w"))

    return path


if not os.path.exists(os.path.join(union_dir, "user_info.json")):
    if not args.f:
        print("Cannot find data/union/user_info.json - Are you in the right folder?")
        should = input("Should i redo the extraction? (y/n): ")
        if should != "y":
            print("ok bye")
            exit()
    users = get_users()
else:
    users = json.load(open(os.path.join(union_dir, "user_info.json"),"r"))

filename = create_union_lists(users,union_size=args.size)
print("Writing path of union list (%s) to file 'union list'" % filename)

with open(os.path.join(union_dir, "union_list_path"),"w") as f:
    f.write(filename)