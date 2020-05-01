#!/usr/bin/env python

import argparse
import datetime
import ipaddress
import os
import subprocess
import re
import yaml
from textfsm import clitable
from netmiko import ConnectHandler, NetMikoAuthenticationException, NetMikoTimeoutException

#Переменные нужные для внутренней работы
DEVICE_FILE = 'devices.yaml'
BACKUP_COMMAND = 'show running-config'
REGEX_ERROR_CLI = re.compile(r'.*(Invalid input detected)|(Incomplete command)|(Ambiguous command).*')
FLAG_BREAK = True



#Функция для считывания и отображения аргументов
def createParser():
    parser = argparse.ArgumentParser(
            prog = 'dev_marafon',
            description= '''
Программа для поиска сетевого обородувания
c заданными параметрами,
передачи команд и снятия резервной копии.
Если сеть не задана берется файл devices.yaml
dev_marafon.py -fp device_params.yaml -shfc show_commands.txt -cnfc conf_commands.txt -net 192.168.100.0/24 -fexip excluded_ip.txt -fb backups'''
            )
    parser.add_argument('-fp','--file_parameters', action="store",
                        dest="file_parameters", help="File with commands")
    parser.add_argument('-shfc','--sh_file_commands', action="store", 
                        dest="sh_file_commands", help="File with show commands")
    parser.add_argument('-cnfc','--conf_file_commands', action="store",
                        dest="conf_file_commands", help="File with conf commands")
    parser.add_argument('-net','--network_subnet', action="store", 
                    dest="network_subnet", help="Network subnet in format X.X.X.X/XX")
    parser.add_argument('-fexip','--file_excluded_ip', action="store",
                    dest="file_excluded_ip", help="File with excluded IP")
    parser.add_argument('-fb','--backup_folder', action="store",
                    dest="backup_folder", help="Folder for backups")
    return parser




#Функция обработки аргументов
def check_parser(parser):
    args = parser.parse_args()
    if not [arg for arg in (vars(args)).values() if arg ]:
        parser.print_help()
        raise Exception("No arguments")
    dict_arg = (vars(args)).copy()
    if args.file_parameters:
        dict_arg['file_parameters']=check_file_parameters(args.file_parameters)
    else:
        print("Без файла параметров невозможно подключиться")
        raise Exception("Script Failed")

    if args.sh_file_commands:
        dict_arg['sh_file_commands']=check_file_commands(args.sh_file_commands)
    else:
        dict_arg['sh_file_commands']=[]

    if args.conf_file_commands:
        dict_arg['conf_file_commands']=check_file_commands(args.conf_file_commands)

    if args.network_subnet:
        dict_arg['network_subnet']=check_network(args.network_subnet)

    elif not check_file_present(DEVICE_FILE):
        print(f"Не указан сеть и отсуствует файл {DEVICE_FILE}")
        raise Exception("Script Failed")

    if not args.backup_folder and not args.conf_file_commands and not args.sh_file_commands:
        print(f"Не указаны команды для передачи")
        raise Exception("Script Failed")

    if args.file_excluded_ip:
        dict_arg['file_excluded_ip']=check_excluded_ip(args.file_excluded_ip)

    return dict_arg


#Функция проверки файла на наличие
def check_file_present(f_present):
    if os.path.isfile(f_present):
        return f_present
    else:
        print(f"Такого файла не существует: {f_present}")


#Функция обработки файла с параметрами подключения к оборудованию
def check_file_parameters(f_parameters):
    if check_file_present(f_parameters):
        with open(f_parameters) as fp:
            dict_params=yaml.safe_load(fp)
        return dict_params


#Функция считывания команд, есть возможность обработки разных разделителей
def check_file_commands(f_commands):
    if check_file_present(f_commands):
        with open(f_commands) as fc:
            list_commands=re.split(r'[\n,;]+', fc.read())
        return list_commands


#Функция обработки файла с исключенными IP адресами
def check_excluded_ip(f_excluded_ip):
    no_f_list_excluded_ip=[]
    list_excluded_ip=[]
    if check_file_present(f_excluded_ip):
        with open(f_excluded_ip) as f:
            no_f_list_excluded_ip=f.read().rstrip().split('\n')
        for ip_excluded in no_f_list_excluded_ip:
            try:
                ipaddress.ip_address(ip_excluded)
                list_excluded_ip.append(ip_excluded)
            except ValueError:
                print(f"In File {f_excluded_ip} unsupport IP: {ip_excluded}")
        return list_excluded_ip


#Функция обработки переменной сети
def check_network(network_subnet):
    try:
        subnet_ip=ipaddress.ip_network(network_subnet)
        return subnet_ip
    except ValueError:
        print(f"Unsupport Network: {network_subnet}")


#Функия считывания из файла IP адресов устройств
def create_ip_list(network_subnet):
    if os.path.isfile(DEVICE_FILE):
        with open(DEVICE_FILE) as f:
            list_ip = yaml.safe_load(f)
        return list_ip

    elif network_subnet:
        subnet_ip = ipaddress.ip_network(network_subnet)
        return subnet_ip.hosts()


#Функция обрабатывает вводные данные проверяет доступность и вызывает функции для подключения к устройствам
def connet_devices(list_ip_devices,file_excluded_ip,sh_file_commands,conf_file_commands,file_parameters,network_subnet,backup_folder):
    list_device_avaliable=[]
    dict_all_result={}
    for ip in list_ip_devices:
        str_ip=str(ip)
        if file_excluded_ip:
            if str_ip in file_excluded_ip:
                continue
        reply = subprocess.run(['fping','-t','200','-r','1',str_ip],stdout=subprocess.DEVNULL)
        if reply.returncode == 0:
            file_parameters['ip']=str_ip
            if backup_folder:
                sh_file_commands.append(BACKUP_COMMAND)
            result = send_show_command(file_parameters,sh_file_commands)
            dict_all_result[str_ip]=result
            list_device_avaliable.append(str_ip)
            if conf_file_commands:
                result_conf = send_config_command(file_parameters,conf_file_commands)
        elif type(list_ip_devices) == list:
            print(f"Device {ip} unreachable")
    with open(DEVICE_FILE, 'w') as f:
        yaml.dump(list_device_avaliable, f)
    return dict_all_result



#Функция отправки show команд
def send_show_command(device,commands):
    try:
        dict_result={}
        ssh= ConnectHandler(**device)
        ssh.enable()
        for command in commands:
            result = ssh.send_command(command)
            dict_result[command]=result
        dict_result['hostname'] = re.sub(r'#', '',ssh.find_prompt())
        return dict_result
    except (NetMikoAuthenticationException, NetMikoTimeoutException)  as except_error:
        print( except_error)


#Функция отправки конфигурационных команд
def send_config_command(device,config_commands):
    try:
        dict_result={}
        ssh= ConnectHandler(**device)
        ssh.enable()
        for commands in config_commands:
            if "ntp server" in commands:
                match = re.match(r'ntp server (\S+)',commands)
                if match:
                    result_ntp = ssh.send_command(f"ping {match.group(1)}")
                    if not "!!!!!" in result_ntp:
                        print(f"NTP Server {match.group(1)} недоступен c {device['ip']}")
                        continue
            result = ssh.send_config_set(commands)
            match = REGEX_ERROR_CLI.search(result)
            if match:
                print(f'Команда "{commands}" выполнилась с ошибкой {match.group(0)} на устройстве {device["ip"]}')
                if FLAG_BREAK:
                    raise Exception("Script Failed")
                dict_result[commands]=match.group(0)
    except (NetMikoAuthenticationException, NetMikoTimeoutException)  as except_error:
        print( except_error)
    print(f"Конфигурация применена на устройство {device['ip']}")



#функция обоработки вывода команд
def re_textfsm(result,templ_path='templates',index_file='index'):
    list_exc=['show running-config','hostname']
    list_dict_out_reg=[]
    for device in result:
        dict_out_reg={}
        for command in result[device]:
            if not command in list_exc:
                attributes =  {'Command': command , 'Vendor': 'cisco_ios'}
                cli_out = clitable.CliTable(index_file, templ_path)
                cli_out.ParseCmd(result[device][command], attributes)
                for out in [list(row) for row in cli_out]:
                    dict_out_reg[command]=out
        dict_out_reg['hostname']=result[device]['hostname']
        dict_out_reg['ip'] = device
        list_dict_out_reg.append(dict_out_reg)
    return list_dict_out_reg



#функция обоработки создания резервных копий вызывает дополнительную функцию
def regex_backup(result,backup_folder):
    for device in result:
        for command in result[device]:
            if "Current configuration" in result[device][command]:
                backup(backup_folder,result[device][command],result[device]['hostname'])
    print("Резервное копирование выполнено")



#функция проверки выполнения резервных копий
def backup(backup_folder,backup_out,device_name):
    today = datetime.datetime.today()
    data = today.strftime("%Y-%m-%d-%H-%M")
    name_file=f"{device_name}-{data}"
    match = re.search(r'.*(Current configuration.*end).*', backup_out,re.DOTALL)
    if match:
        if not os.path.exists(backup_folder):
            os.mkdir(backup_folder)
        with open (f"{backup_folder}/{name_file}",'w') as dest:
            dest.write(match.group(1))
    else:
        print(f"Config file not all!!!:\n{backup_out}")


#Финальная функция обрабатывает все под вывод в задании
def final(list_of_all):
   for device_result in list_of_all:
        device_print = {}
        device_print['hostname'] = device_result['hostname']
        device_print['out_sh_ver'] = '-'.join(device_result['show version'][:-1])
        device_print['out_model'] = device_result['show version'][-1]
        if 'K9' in device_result['show version']:
            device_print['Encryption'] = 'PE'
        else:
            device_print['Encryption'] = 'NPE'
        if 'synchronized' in device_result['show ntp status']:
            device_print['out_ntp'] = 'Clock in Sync'
        elif 'unsynchronized' in device_result['show ntp status']:
            device_print['out_ntp'] = 'Clock not  Sync'
        if device_result.get('show cdp neighbors'):
            device_print['out_cdp'] = f'CDP is ON, {device_result["show cdp neighbors"][0]} peers'
        elif device_result.get('show cdp'):
            if 'not enabled' in device_result['show cdp']:
                device_print['out_cdp'] = f'CDP is OFF'
        print("{hostname}|{out_model}|{out_sh_ver}|{Encryption}|{out_cdp}|{out_ntp}".format(**device_print))



#Основная функция
def main_fuction(dict_all_params):
    list_ip_devices = create_ip_list(dict_all_params['network_subnet'])
    if not dict_all_params['sh_file_commands']:
        if not dict_all_params['conf_file_commands']:
            if dict_all_params['backup_folder']:
                result = connet_devices(list_ip_devices,**dict_all_params)
                regex_backup(result,dict_all_params['backup_folder'])
                return
        else:
            result = connet_devices(list_ip_devices,**dict_all_params)
            if dict_all_params['backup_folder']:
                regex_backup(result,dict_all_params['backup_folder'])
            return
    result = connet_devices(list_ip_devices,**dict_all_params)
    if dict_all_params['backup_folder']:
        regex_backup(result,dict_all_params['backup_folder'])
    list_all_result = re_textfsm(result)
    final(list_all_result)


if __name__ == '__main__':


    parser = createParser()
    pr = check_parser(parser)
    main_fuction(pr)
