#!/usr/bin/env python

from nornir import InitNornir
from nornir.plugins.tasks.networking import netmiko_send_command
import os
import re
import graphviz as gv
import yaml


#Основные переменные
os.environ["NET_TEXTFSM"]='./ntc-templates/templates' #Прописываем путь к шаблонам TEXTFSM
save_old_result = "old_result.yaml" #Имя файла, где сохраняем "старую топологию"
save_new_result = "new_result.yaml" #Имя файла, где сохраняем "текущую топологию"

#Словарь с описанием базовых настроек для отображения в graphviz
styles = {
    "graph": {
        "label": "Network Topology",
#Размер шрифта для надписи
        "fontsize": "14",
        "fontcolor": "Black",
#Направление заполнения
        "rankdir": "LR",
#        "size":"15,10",
#Заполнение
        "ratio":"fill",
        "nodesep":"1",
        "ranksep":"1",
        "splines":"ortho",
    },
    "nodes": {
        "fontcolor": "red",
        "labelloc":"b",
        "margin": "0.4",
    },
    "edges": {
        "style": "bold",
        "color": "black",
        "fontname": "Courier",
        "fontsize": "12",
        "fontcolor": "blue",
    },
}

def start_nornir():
'''Основная  функция
'''

'''Словарь куда будем записывать вывод Norinr'''
    dict_new = {}
    nr = InitNornir(config_file="config.yaml")
    results_all =  nr.run(netmiko_send_command, command_string = f'show lldp neig', use_textfsm=True)

    for host in results_all.keys():
        for result in results_all[host]:
            dict_new[host]=result.result
'''ираем из функции словари с соединениями и соотвестиями'''
    d_output,d_capability=create_dict_draft(dict_new)
'''едаем словари в функции для графического вывода топологии'''
    draw_topology(d_output,d_capability)
'''Передаем в функцию вывод с Nornir и получаем предыдущую топологию'''
    d_file_old = check_file_parameters(dict_new)
'''Проверяем была ли предыдущая топология сохранена и если да
    то передаем ее в начале в функцию для определения изменения топологии
    а затем для отрисовки изменений'''
    if d_file_old:
        dict_diff=check_topology(d_output,d_capability,d_file_old)
        draw_topology(dict_diff,d_capability,out_filename="img/topology_diff")




def create_dict_draft(result):
'''Функция для создания словарей для отрисовки топологии
'''
'''Создаем словарь с соединениями'''
    dict_graf={}
'''Создаем словарь с соотвествием имя-модель'''
    dict_capability={}
    for device in result:
        for r_list in result[device]:
'''Убираем доменное имя из имени устройства в neighbor'''
            match=re.match(r'(\S+)\.home.local',r_list['neighbor'])
            if match:
                name_device=match.group(1)
            else:
                name_device=r_list['neighbor']
'''Собираем словарь к виду ('r10', 'Et0/0'): ('sw2', 'Et0/2').'''
            dict_graf[(device.lower(),r_list['local_interface'])]=(name_device.lower(),r_list['neighbor_interface'])
"""Собираем словарь соотвествий к виду 'sw3': 'R'"""
            dict_capability[name_device.lower()]=r_list['capabilities']
'''Создаем словарь, для того чтобы убрать все дубликаты'''
    dict_graf_out={}
    for k in dict_graf.keys():
        if not k in list(dict_graf_out.values()):
            dict_graf_out[k]=dict_graf[k]
'''Возвращаем словарь соединений и словарь соотвествий'''
    return dict_graf_out,dict_capability




def check_file_parameters(result_ditc):
'''Функция для сохранения данных вывода в файлы.
'''
'''Проверяем есть ли файл save_new_result'''
    if os.path.isfile(save_new_result):
'''Если да, то мы переименовываем его в save_old_result
тем самым мы сохраняем предыдущую топологию
'''
        os.rename(save_new_result,save_old_result)
'''Сохраняем текущий вывод из Nornir в YAML формат.'''
    with open(save_new_result, 'w') as f:
        yaml.dump(result_ditc, f)
'''И считываем предыдущую топологию если такова существует'''
    if os.path.isfile(save_old_result):
        with open(save_old_result) as fp:
            old_result_dict=yaml.safe_load(fp)
        return old_result_dict


def check_topology(d_output,d_capability,old_result_dict):
'''Функция для выявления изменений в топологии и собрание их в словарь
'''
'''Передаем в функцию create_dict_draft вывод старой топологии и 
   получаем два словаря с соединениями и соотвествеем
'''
    dict_result_old,dict_capability_old = create_dict_draft(old_result_dict)
'''Производим логическое сравнение и оставляем все непересекающиеся значения'''
    diff_dicts = d_output.items() ^ dict_result_old.items()
'''Создаем словарь в который будем записывать изменения'''
    dict_diff={}
    for key in diff_dicts:
        if key in dict_result_old.items():
            print(f'{key} соединение удалено')
        elif key in d_output.items():
            print(f'{key} соединение добавлено')
        dict_diff[key[0]] = key[1]
    return dict_diff


def apply_styles(graph, styles):
'''Вспомогательная функция для визуализации'''
    graph.graph_attr.update(("graph" in styles and styles["graph"]) or {})
    graph.node_attr.update(("nodes" in styles and styles["nodes"]) or {})
    graph.edge_attr.update(("edges" in styles and styles["edges"]) or {})
    return graph


def draw_topology(topology_dict, capability_dict, out_filename="img/topology", style_dict=styles):
    """
        {('R4', 'Eth0/1'): ('R5', 'Eth0/1'),
         ('R4', 'Eth0/2'): ('R6', 'Eth0/0')}

    соответствует топологии:
    [ R5 ]-Eth0/1 --- Eth0/1-[ R4 ]-Eth0/2---Eth0/0-[ R6 ]

    Функция генерирует топологию, в формате svg.
    И записывает файл topology.svg в каталог img.
    """
    nodes = set(
        [item[0] for item in list(topology_dict.keys()) + list(topology_dict.values())]
    )

    graph = gv.Graph(format="svg")

    for node in nodes:
        graph.node(node,label=f'\n\n\n{node}',shapefile=f'{capability_dict[node]}.png')

    for key, value in topology_dict.items():
        head, t_label = key
        tail, h_label = value
        graph.edge(head, tail, headlabel=h_label, taillabel=t_label, label=" " * 15)

    if os.path.isfile(f'{out_filename}.svg'):
        os.rename(f'{out_filename}.svg',f'{out_filename}_old.svg')

    graph = apply_styles(graph, style_dict)
    filename = graph.render(filename=out_filename)
    print("Topology saved in", filename)



if __name__ == '__main__':
    start_nornir()
