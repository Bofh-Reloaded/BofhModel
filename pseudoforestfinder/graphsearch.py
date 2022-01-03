# -*- coding: utf-8 -*-
"""
Spyder Editor

"""

import networkx as nx

##uncomment if using loaded matrix
#from load_bsc_pools_graph import load_graph_from_json_coso 

#the_graph = load_graph_from_json_coso()

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
        tc_nodes = set(set(graph.predecessors(stable_node)) & set(successorslist))
        for tc_node in tc_nodes:
            path = [start_node, tc_node, stable_node, start_node]
            path_list.append(path)
    return path_list

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


def compute_weights_in_path(path,graph):
    cost = 0
    for x in range(0,len(path)-1):
       cost = cost + get_edge_weight(graph, path[x], path[x+1], "weight")
    return cost


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
G = the_graph

print("number of nodes: ", G.number_of_nodes())
print("number of edges: ", G.number_of_edges())
#for line in nx.generate_edgelist(the_graph):
#   if line[0] == 2:
#       print(line)
    
stable_nodes = [420608,4,377192,5, 489332, 451609]
start_node = 2 
#print(nx.is_directed(G))
#nx.draw(the_graph, pos=nx.circular_layout(the_graph), node_color='r', edge_color='b') #draw graph 
#pred=G.predecessors(1)
#for x in range(1,506626):
#    for path in nx.all_simple_paths(the_graph, source=x, target=6): 
#        print(len(path))
#        if len(path)<7:
       #     print(path, " cost is:", the_graph.subgraph(path).size(weight="weight"))
#nx.draw(G.subgraph(path), pos=nx.circular_layout(G.subgraph(path)), node_color='r', edge_color='b')


possible_paths_2 = find_all_paths_2way_var(G, start_node, stable_nodes)
possible_paths_3 = find_all_paths_3way_var(G, start_node, stable_nodes)
possible_paths_4 = find_all_paths_4way_var(G, start_node, stable_nodes)
print("The number of possible 2-way exchanges starting from node", start_node, " is: ", len(possible_paths_2))
print("Printing the list of possible paths and their cost:")
for analyzed_path in possible_paths_2:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    print(analyzed_path)
print("The number of possible 3-way exchanges starting from node", start_node, " is: ", len(possible_paths_3))
print("Printing the list of possible paths and their cost:")
for analyzed_path in possible_paths_3:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    print(analyzed_path)
print("The number of possible 4-way exchanges starting from node", start_node, " is: ", len(possible_paths_4))
print("Printing the list of possible paths and their cost:")
for analyzed_path in possible_paths_4:
    #print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
    print(analyzed_path)

#for x in range(1,7):
#    possible_paths = find_all_paths_var(G, x, stable_nodes)
#    print("The number of possible 4-way exchanges starting from node", x, " is: ", len(possible_paths))
#    print("Printing the list of possible paths and their cost:")
#    for analyzed_path in possible_paths:
#         print(analyzed_path, "cost is:", compute_weights_in_path(analyzed_path, G))
        
    
    
