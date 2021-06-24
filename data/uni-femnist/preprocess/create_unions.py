# Takes a large json file of users and their data and creates unions

from __future__ import division
import json
import math
import numpy as np
import os
import sys

if not os.path.exists("data/union/user_info.json"):
    print("Cannot find data/union/user_info.json - Are you in the right folder?")
    should = input("Should i redo the extraction? (y/n): ")
    if should == "y":
        data = json.load(open("data/all_data/all_data_0.json","r"))
        data.pop('user_data', None)
        json.dump(data, open("data/union/user_info.json","w"))
    else:
        print("bye")
        exit()

users = json.load(open("data/union/user_info.json","r"))

def equal_unions(users, union_size=0.05):
    # Returns a list of (1/num_union) lists with user_ids

    shuffle_seed = 9873248
    np.random.seed(shuffle_seed)

    num_unions = math.ceil(1/union_size)
    
    user_ids = users["users"]
    num_samples = list(map(int, users["num_samples"]))
    sample_dict = dict(zip(user_ids,num_samples))
    
    ids = np.array(user_ids)
    np.random.shuffle(ids)

    unions = [[] for _ in range(num_unions)]

    for i,u in enumerate(ids):
        unions[i%num_unions].append(u)

    if False:
        for union in unions:
            total = 0
            for user in union:
                total += sample_dict[user]
            print(total)

    return unions


def create_union_lists(users, union_type="equal", union_size=0.05):
    if union_type == "equal":
        unions = equal_unions(users,union_size)

    filename = "data/union/union_lists_%s_%s.json" % (union_type, union_size)
    json.dump(unions, open(filename,"w"))

create_union_lists(users)