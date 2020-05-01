#!/usr/bin/env python

from nornir import InitNornir
from nornir.plugins.tasks.networking import netmiko_send_command
from nornir.core.filter import F
from netaddr import *
import os

os.environ["NET_TEXTFSM"]='./ntc-templates/templates'


def input_mac():
    
    while True:
        macaddress = input("Введите MAC адрес: ")
        try:
            macadr_cisco = EUI(macaddress)
        except AddrFormatError:
            print(f"Неправильный формат MAC адреса {macaddress}")
        else:
            macadr_cisco.dialect = mac_cisco
            return macadr_cisco


def mac_nornir(mac_address):
    if not mac_address:
        print("MAC адрес не передан")
        return

    nr = InitNornir(config_file="config.yaml")

    switches= nr.filter(F(tags__all = ['switches']))

    results_sw = switches.run(netmiko_send_command, command_string = f'show mac address-table  address {mac_address}', use_textfsm=True)

    dict_device={}

    for device, result_sw in results_sw.items():
        dict_result = result_sw[0].result[0]
        if type(dict_result) is  dict:
            dict_device[device]=(result_sw[0].result[0]).copy()

    switches_int = switches.filter(filter_func=lambda h: h.name in list(dict_device.keys()))
    ''' Можно было бы не запрашивать все интерфейсы
        а забрать только те где был обнаружен мак адрес
        но я так и не нашел как подставлять в команду переменные'''


    results_sw_int = switches_int.run(netmiko_send_command, command_string = f'show interfaces switchport', use_textfsm=True)


    for device,result_sw_int in results_sw_int.items():
        for dict_int in result_sw_int[0].result:
            if dict_int['interface'] == dict_device[device]['destination_port']:
                if 'access' in dict_int['mode']:
                    print(f'MAC address {mac_address} on  Switch {device} Port {dict_int["interface"]}')
    

if __name__ == '__main__':
    mac_nornir(input_mac())
