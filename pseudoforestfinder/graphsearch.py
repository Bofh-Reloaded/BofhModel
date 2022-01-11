# -*- coding: utf-8 -*-
"""
Spyder Editor

"""

#import networkx as nx

##uncomment if using loaded matrix
#from load_bsc_pools_graph import load_graph_from_json_coso 

#the_graph = load_graph_from_json_coso()
import sys
from load_from_status_db import load_graph_from_db_directory
from load_from_status_db import load_predicted_swap_events

the_graph = load_graph_from_db_directory("./dbswap/dbswap")

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
    usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    for stable_node in usable_nodes:
        tc_nodes = set(graph.predecessors(stable_node)) & set(successorslist)
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
    usable_nodes = (set(stable_list) & (predecessorslist)) #filter blue arrows on stable nodes
    for stable_node in usable_nodes:
            path = [start_node, stable_node, start_node]
            path_list.append(path)
    return path_list

#Utility functions
def get_edge_weight(graph,start,end,key):
    dict = graph[start][end]
    return dict[0][key]

def get_edge_pool(graph,start,end,key):
    dict = graph[start][end]
    mypool = dict[0][key]
    print(mypool.address)
    if mypool.reserve1 == 0 :
        raise Exception ('Found empty reserve in liquidity pool') 
    #ratio = mypool.reserve0/mypool.reserve1
    ratio = mypool
    #if ratio >= mypool.reserve0:
        #exchange for next swap my pool.reserve0
    #else #exchange ratio 
    return ratio

#Computes the revenue for a triangular exchange
def compute_weights_in_path(path,graph,fee):
    amount = sys.maxsize
    
    try:
        start_pool = get_edge_pool(graph, path[0], path[1], 'pool')
        start_amount = max_flux(start_pool)
        if start_amount == 0:
            return (-2,0,0)
        for x in range(0,len(path)-1):
         
            pool = get_edge_pool(graph, path[x], path[x+1], "pool")
        #if pool_cost == -1:
         #   return -1
        #cost = cost * pool_cost
            amount = min(amount,max_flux(pool))            
            amount = gain_per_edge(pool, amount, fee)
    except:
        return (-1,0,0)
    return ((amount/start_amount), amount, start_amount)


def gain_per_edge(pool,amount,fee):
    return amount * pool.reserve1/pool.reserve0 * (1-fee)

def max_flux(pool):
    return abs(pool.reserve1 - pool.reserve0)/3
    
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
    

#Generating the graph of example on draw.io
#G = nx.MultiDiGraph()

#G.add_nodes_from([1,2,3,4,5,6])



#edges = G.add_edge(1,2,weight=1)
#edges = G.add_edge(1,4,weight=1)
#edges = G.add_edge(2,4,weight=1)
#edges = G.add_edge(3,1,weight=1)
#edges = G.add_edge(3,5,weight=1)
#edges = G.add_edge(3,6,weight=1)
#edges = G.add_edge(4,1,weight=1)
#edges = G.add_edge(4,2,weight=1)
#edges = G.add_edge(4,3,weight=1)
#edges = G.add_edge(4,5,weight=1)
#edges = G.add_edge(4,6,weight=1)
#edges = G.add_edge(5,3,weight=1)
#edges = G.add_edge(5,6,weight=1)
#edges = G.add_edge(6,1,weight=1)

##Uncomment if using the loaded matrix
G = the_graph

print("number of nodes: ", G.number_of_nodes())
print("number of edges: ", G.number_of_edges())

#stable_nodes = [i for i in range(1, 626199)]    
stable_nodes = [420608,4, 377192, 2, 5, 258, 489332, 451609, 611173, 604407, 538538, 623880, 374437, 3, 13, 515506, 31, 34, 29]
start_node = 4
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
possible_paths_2 = find_all_paths_2way_var(G, start_node, stable_nodes)
possible_paths_3 = find_all_paths_3way_var(G, start_node, stable_nodes)
#possible_paths_4 = find_all_paths_4way_var(G, start_node, stable_nodes)
print("The number of possible 2-way exchanges starting from node", start_node, " is: ", len(possible_paths_2))
print("Printing the list of possible paths and their cost:")
for analyzed_path in possible_paths_2:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    print(analyzed_path)
print("The number of possible 3-way exchanges starting from node", start_node, " is: ", len(possible_paths_3))
print("Printing the list of possible paths and their cost:")
arbitrage_opportunity = []
file = open ('3waystest.txt','w')
for analyzed_path in possible_paths_3:
    weight,amount,start_amount = compute_weights_in_path(analyzed_path, G,0.003)
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    #print(analyzed_path)
    #file.write(repr(analyzed_path) + " total unbalance: " + repr(compute_weights_in_path(analyzed_path, G)) + '\n')
    #file.write(repr(analyzed_path) + " total unbalance: " + repr(compute_weights_in_path(analyzed_path, G,0.003)) + '\n')
    if weight >= 1:
        file.write(f" {analyzed_path} total unbalance: {weight:.3} : {start_amount:.3} -> {amount:.3} \n")
        arbitrage_opportunity.append(analyzed_path)
file.close()

#print("The number of possible 4-way exchanges starting from node", start_node, " is: ", len(possible_paths_4))
#print("Printing the list of possible paths and their cost:")
#for analyzed_path in possible_paths_4:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    #print(analyzed_path)


        
    
    
