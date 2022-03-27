# -*- coding: utf-8 -*-
"""
Spyder Editor

"""

import networkx as nx

##uncomment if using loaded matrix
#from load_bsc_pools_graph import load_graph_from_json_coso

#the_graph = load_graph_from_json_coso()
import sys
from load_from_status_db import load_graph_from_db_directory, get_start_node_id, get_stable_nodes_id

#the_graph = load_graph_from_db_directory("./dbswap/dbswap")

#Core function to find all possible 4-way exchanges in "graph" starting and coming back to "start node"
def find_all_paths_4way(graph, start_node, stable_list):
    path_list = []
    for out_node in graph.successors(start_node): #list the nodes reached from starting node: starting direct tree
        for in_node in stable_list: #list of nodes arriving in starting nodes: starting inverse tree
            #print("Predecessor of: ", in_node, " is ", out_node)
            if (in_node in graph.predecessors(start_node)) & (in_node != out_node): #only consider stable tokens for inverse tree
                for tc_node in graph.predecessors(in_node): #find nodes connecting the direct and inverse tree
                    if out_node in graph.predecessors(tc_node):
                        path = [start_node, out_node, tc_node, in_node, start_node] #make list of nodes
                        path_list.append(path)
            #else: print("not in stable list")
    return path_list

#Variation of the find_all_paths which exploits set intersection instead of iterative search (faster but requires more memory)
def find_all_paths_4way_var(graph, start_node, stable_list):
    path_list = []
    successorslist = set(graph.successors(start_node))
    predecessorslist = set(graph.predecessors(start_node))
    print("number of successors: ", len(successorslist)) #green arrows - forward path
    print("number of predecessors: ", len(predecessorslist)) #blue arrows - reverese path
    usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    #print("usable_nodes: ", list(usable_nodes))
    for stable_node in usable_nodes:
        for second_node in successorslist:
            if stable_node != second_node: #avoid cycling on two nodes iteratively
                tc_nodes = set((graph.successors(second_node))) & set((graph.predecessors(stable_node))) #search the nodes connecting the forward and reverse path
                #print ("The list of tc nodes is: ", tc_nodes)
                for tc_node in tc_nodes: #if the tc nodes exist, save the paths
                    path = [start_node, second_node, tc_node, stable_node, start_node]
                    path_list.append(path)
    return path_list

#Function to find all possible 3-way exchanges passing through stable nodes.
def find_all_paths_3way_var(graph, start_node, stable_list):
    path_list = []
    successorslist = set(graph.successors(start_node))
    predecessorslist = set(graph.predecessors(start_node))
    print("number of successors: ", len(successorslist)) #green arrows - forward path
    print("number of predecessors: ", len(predecessorslist)) #blue arrows - reverese path
    #usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    usable_nodes = ((predecessorslist)) #filter blue arrows on stable nodes
    #print("usable_nodes: ", list(usable_nodes))
    for stable_node in usable_nodes:
        #tc_nodes = set(graph.predecessors(stable_node)) & set(successorslist)
        tc_nodes = set(successorslist)
        for tc_node in tc_nodes:
            path = [start_node, tc_node, stable_node, start_node]
            path_list.append(path)
    return path_list
#Function to find all possible 2-way exchanges passing through stable nodes. (Same as GO code.)
def find_all_paths_2way_var(graph, start_node, stable_list):
    path_list = []
    successorslist = set(graph.successors(start_node))
    predecessorslist = set(graph.predecessors(start_node))
    print("number of successors: ", len(successorslist)) #green arrows - forward path
    print("number of predecessors: ", len(predecessorslist)) #blue arrows - reverese path
    #usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    usable_nodes = set(predecessorslist) #filter blue arrows on stable nodes
    #print("usable_nodes: ", list(usable_nodes))
    for stable_node in usable_nodes:
            path = [start_node, stable_node, start_node]
            path_list.append(path)
    return path_list


def reach_pool_from_node_right(graph, token_b, token_start):
    succ_list = list(graph.successors(token_b))
    print(f"successors of {token_b}: {succ_list}")
    if token_start in succ_list:
        return [token_b,token_start]
    else:
        temp_list = []
        print(f"looking in {succ_list}");
        for token in succ_list:
            print(f"trying {token} for {token_b}")
            temp_list = reach_pool_from_node_right(graph, token, token_start)
            if temp_list:
                temp_list.insert(0, token_b)
                break
        print(f"found {temp_list}")
        return temp_list
 
#returns the full right fan 
def reach_pool_from_node_right_all(graph, token_b, token_start):
    paths_right = []
    succ_list = list(graph.successors(token_b))
    print(f"successors of {token_b}: {succ_list}")
    if token_start in succ_list:
        return [token_b,token_start]
    else:
        temp_list = []
        print(f"looking in {succ_list}");
        for token in succ_list:
            print(f"trying {token} for {token_b}")
            temp_list = reach_pool_from_node_right(graph, token, token_start)
            if temp_list:
                temp_list.insert(0, token_b)
                paths_right.append(temp_list)
        print(f"found {temp_list}")
        return paths_right   
    

def reach_pool_from_node_left(graph, token_a, token_start):
    pred_list = list(graph.predecessors(token_a))
    print(f"predecessors of {token_a}: {pred_list}")
    if token_start in pred_list:
        return [token_start, token_a]
    else:
        temp_list = []
        print(f"looking in {pred_list}");
        for token in pred_list:
            print(f"trying {token} for {token_a}")
            temp_list = reach_pool_from_node_left(graph, token, token_start)
            if temp_list:
                temp_list.append(token_a)
                break
        print(f"found {temp_list}")
        return temp_list
 
#retunrs the full left fan    
def reach_pool_from_node_left_all(graph, token_a, token_start):
    paths_left = []
    pred_list = list(graph.predecessors(token_a))
    print(f"predecessors of {token_a}: {pred_list}")
    if token_start in pred_list:
        return [token_start, token_a]
    else:
        temp_list = []
        print(f"looking in {pred_list}");
        for token in pred_list:
            print(f"trying {token} for {token_a}")
            temp_list = reach_pool_from_node_left(graph, token, token_start)
            if temp_list:
                temp_list.append(token_a)
                paths_left.append(temp_list)
        print(f"found {temp_list}")
        return paths_left    
    

def reach_pool_from_node(graph, token_a, token_b, token_start, level=0):
    print(f"find {token_start} to {token_a},{token_b}")
    temp_list_right =  reach_pool_from_node_right(graph, token_b, token_start)
    if not temp_list_right:
        return []
    temp_list_left=reach_pool_from_node_left(graph, token_a, token_start)
    if not temp_list_left:
        return temp_list_left
    return temp_list_left + temp_list_right

#Utility functions
def get_edge_weight(graph,start,end,key):
    dict = graph[start][end]
    return dict[0][key]

def find_all_paths_through_pool(graph, token_a, token_b, token_start):
    path_list = []
    left_paths = []
    right_paths = []
    pred_list = graph.predecessors(token_a)
    succ_list = graph.successors(token_b)
    #find all left paths
    for pred_token in pred_list:
        if pred_token == token_start:
            left_paths.append([token_start,token_a])
        else:
            temp_paths = reach_pool_from_node_left_all(graph, pred_token, token_start)
            for temp_path in temp_paths:
                if temp_path:
                    left_paths.append([temp_path,token_a])
    #find all right paths
    for succ_token in succ_list:
        if succ_token == token_start:
            right_paths.append([token_b,token_start])
        else:
            temp_paths = reach_pool_from_node_right_all(graph, succ_token, token_start)
            for temp_path in temp_paths:
                if temp_path:
                    right_paths.append([token_b,temp_path])
    #mix all paths as all possible paths            
    for path_left in left_paths:
        for path_right in right_paths:
            path_list.append(path_left+path_right)
    return path_list
    

#lists the pools connecting two tokens (generally from different exchanges)
def get_edge_pool(graph,start,end,key):
    pools = []
    edges = graph[start][end]
    for edge in edges.values():
        mypool = edge[key]
    #print(mypool.address)
        if mypool.reserve1 == 0:
            continue
        pools.append(mypool)
    if len(pools) == 0:
        raise Exception ('Found empty reserve in liquidity pool')

    #if len(pools) > 1:
     #   print("Found multi-exchange pool on " + str(len(pools)) + " exchanges" )

    return pools

def find_all_paths_multi_exchange(graph,paths):
    path_list = []
    for path in paths:
        try:
            for start_pool in get_edge_pool(graph, path[0], path[1], 'pool'):
                for second_pool in get_edge_pool(graph, path[1], path[2], 'pool'):
                    for third_pool in get_edge_pool(graph, path[2], path[0], 'pool'):
                        path_list.append(path)
        except: path_list.append([0,0,0,0])
    return path_list


#Computes the revenue for a triangular exchange
def compute_weights_in_path(path,graph,fee):
    amount = sys.maxsize
    pools = []
    try:
        max_amount = 0
        max_pool = None
        for start_pool in get_edge_pool(graph, path[0], path[1], 'pool'):
            start_amount = max_flux(start_pool)
            if max_amount < start_amount:
                max_amount = start_amount
                max_pool = start_pool

        start_amount = max_amount
        pools.append(max_pool.address)

        if start_amount == 0:
            return (-2,0,0,[])

        for x in range(0,len(path)-1):
            max_amount = 0
            max_pool = None
            for pool in get_edge_pool(graph, path[x], path[x+1], "pool"):
                amount = min(amount, max_flux(pool))
                amount = gain_per_edge(pool, amount, fee)
                if max_amount < amount:
                    max_amount = amount
                    max_pool = pool

            amount = max_amount
            pools.append(max_pool.address)

    except:
        return (-1,0,0,[])
    return ((amount/start_amount), amount, start_amount, pools)


#Get the gain on each edge. To be updated to get the fee from the pool object
def gain_per_edge(pool,amount,fee):
    return amount * pool.reserve1/pool.reserve0 * (1-fee)

#temporary, to be updated with C++ code
def max_flux(pool):
    return abs(pool.reserve1 - pool.reserve0)/3

#to be implemented following C++ code
def max_flux_on_path(path):
    return 0

#not used for now - to be debugged
def automagical_formula_3_way (r1,r2,path, graph, delta):
    dict = graph[path[0]][path[1]]
    mypool = dict[0]['pool']
    a1 = mypool.reserve0
    b1 = mypool.reserve1
    dict = graph[path[1]][path[2]]
    mypool = dict[0]['pool']
    b2 = mypool.reserve0
    c2 = mypool.reserve1
    dict = graph[path[2]][path[3]]
    mypool = dict[0]['pool']
    c3 = mypool.reserve0
    a3 = mypool.reserve1
    checksum = a1*b1*b2*c2*c3*a3
    if checksum == 0:
        return -1
    gain = (r1 * r2 * ((r1**2 * r2**2 * b1 * c2 * a3)/(b2*c3+r1*r2*b1*c3*r1**2*r2**2*b1*c2)/((a1*b2*c3))/(b2*c3+r1*r2*b1*c3+r1**2*r2**2*b1*c2)+r1*delta)-1)*delta
    return gain

#utility functions
def read_paths_from_file (file):
    buffer = open(file, "r")
    content = buffer.read()
    content_list = content.split("\n")
    # print(len(content_list))
    buffer.close()
    return content_list


def extract_differences (file1, file2) :
    list1 = read_paths_from_file(file1)
    list2 = read_paths_from_file(file2)
    if len(list1) > len(list2):
        return set(list1) - set(list2)
    return set(list2) - set(list1)

#Generating the graph of example on draw.io
G = nx.MultiDiGraph()

G.add_nodes_from([1,2,3,4,5,6])



edges = G.add_edge(1,2,weight=1)
edges = G.add_edge(1,4,weight=1)
edges = G.add_edge(2,4,weight=1)
edges = G.add_edge(3,1,weight=1)
edges = G.add_edge(3,5,weight=1)
edges = G.add_edge(3,6,weight=1)
edges = G.add_edge(4,1,weight=1)
edges = G.add_edge(4,2,weight=1)
edges = G.add_edge(4,3,weight=1)
edges = G.add_edge(4,5,weight=1)
edges = G.add_edge(4,6,weight=1)
edges = G.add_edge(5,3,weight=1)
edges = G.add_edge(5,6,weight=1)
edges = G.add_edge(6,1,weight=1)

##Uncomment if using the loaded matrix
#G = the_graph
#print("G.has_edge(2, 4)", G.has_edge(2, 4))
#print("G.has_edge(4, 2)", G.has_edge(4, 2))

print("number of nodes: ", G.number_of_nodes())
print("number of edges: ", G.number_of_edges())

#print(reach_pool_from_node(G, 5, 3, 1))
print(find_all_paths_through_pool(G, 3, 6, 1))


pools_per_node = dict()
for node in G.nodes():
    edges = G.edges(node)
    l = len(edges)
    if l > 2:
        for edge in edges:
            l = len(G[node][edge[1]])
            if l > 1:
                pools_per_node[(node, edge[1])] = l

# print(f"{len(pools_per_node)} pools with more than 1 exchange {max(pools_per_node)} {min(pools_per_node)}")

#stable_nodes = [i for i in range(1, 626199)]

try:
    start_node = get_start_node_id()
    stable_nodes = get_stable_nodes_id()
    print("using db start_node", start_node)
    print("using db stable_nodes", stable_nodes)
except:
    stable_nodes = [420608, 4, 377192, 2, 5, 258, 489332, 451609, 611173, 604407, 538538, 623880, 374437, 3, 13, 515506,
                    31, 34, 29]
    start_node = 2
    print("using hardwired start_node", start_node)
    print("using hardwired stable_nodes", stable_nodes)



#print("List of predecessors is", set(G.predecessors(1)))
#print(nx.is_directed(G))
#nx.draw(the_graph, pos=nx.circular_layout(the_graph), node_color='r', edge_color='b') #draw graph
#pred=G.predecessors(1)
#for x in range(1,506626):
#    for path in nx.all_simple_paths(the_graph, source=x, target=6):
#        print(len(path))
#        if len(path)<7:
       #     print(path, " cost is:", the_graph.subgraph(path).size(weight="weight"))
#nx.draw(G.subgraph(path), pos=nx.circular_layout(G.subgraph(path)), node_color='r', edge_color='b')

#print(get_edge_pool(G, 13, 4, "pool").reserve0)
#possible_paths_2 = find_all_paths_2way_var(G, start_node, stable_nodes)
#possible_paths_3 = find_all_paths_3way_var(G, start_node, stable_nodes)
#possible_paths_4 = find_all_paths_4way_var(G, start_node, stable_nodes)
#print("The number of possible 2-way exchanges starting from node", start_node, " is: ", len(possible_paths_2))
#print("Printing the list of possible paths and their cost:")
#for analyzed_path in possible_paths_2:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
#    print(analyzed_path)
#print("The number of possible 3-way exchanges starting from node", start_node, " is: ", len(possible_paths_3))
#print("Printing the list of possible paths and their cost:")
arbitrage_opportunity = []

#with open('3waystest.txt','w') as file:
#    for analyzed_path in possible_paths_3:
#        weight,amount,start_amount,pools = compute_weights_in_path(analyzed_path, G,0.003)
        #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
        #print(analyzed_path)
        #file.write(repr(analyzed_path) + " total unbalance: " + repr(compute_weights_in_path(analyzed_path, G)) + '\n')
        #file.write(repr(analyzed_path) + " total unbalance: " + repr(compute_weights_in_path(analyzed_path, G,0.003)) + '\n')
        #print(f"{weight} {pools}")
        #print(f" {analyzed_path} total unbalance: {weight:.3} : {start_amount:} -> {amount:}, {pools}", file=file)
 #       if weight >= 1:
            #print(f"{weight:.3} {pools}")
 #           print(f" {analyzed_path} total unbalance: {weight:.3} : {start_amount:.3} -> {amount:.3}, {pools}", file=file)
 #           arbitrage_opportunity.append(analyzed_path)
  #      else:
  #          print(f" {analyzed_path} total unbalance: {weight:} : {start_amount:} -> {amount:}, {pools}", file=file)
#full_path_list = find_all_paths_multi_exchange(G, possible_paths_3)
#with open('fullpathlist.txt','w') as file:
#    for path in full_path_list:
#        print(f"{path}",file=file)
#print ('The difference is: ',extract_differences('3waystest.txt','3waystestmod.txt' ))
#print("The number of possible 4-way exchanges starting from node", start_node, " is: ", len(possible_paths_4))
#print("Printing the list of possible paths and their cost:")
#for analyzed_path in possible_paths_4:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    #print(analyzed_path)

