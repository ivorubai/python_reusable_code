#!/usr/bin/python
from api_helper import APIHelper
import re
import time
from random import choice, randint
import threading
from functools import wraps

def add_ldev_id_in_hex(fn):
    @wraps(fn)
    def inner(*args,**kwargs):
        volumes = fn(*args,**kwargs)
        for volume in volumes:
            if volume:
                volume["ldevIdInHex"] = f"{volume['ldevId']:04X}"
        return volumes
    return inner

class HitachiBoxAPI(APIHelper):
    volume_given_for_svol = set()
    lock = threading.Lock()

    def __init__(self, ip, username, password, base_api='/ConfigurationManager/v1/objects'):
        super().__init__(ip, username, password, base_api)

        ## Hitachi Box specific state
        self._pool_name = None
        self._device_id = None
        self._pools = None
        self._port_ids = None
        self._host_groups = None

        self._iscsi_port_ids = None
        self._fc_port_ids = None

        self.sessionid = None
        self.token = None
        self.login(endpoint='/sessions')

    ############################# USEFUL PROPERTY #############################################

    @property
    def pool_name(self):
        return self._pool_name

    @pool_name.setter
    def pool_name(self, name):
        if isinstance(name,str) and name:
            self._pool_name = name

    @property
    def device_id(self):
        if not self._device_id:
            data = self.get_storages()
            self._device_id = data[0]["storageDeviceId"]  # raises KeyError if key is missing
        return self._device_id

    @property
    def pools(self):
        if not self._pools:
            self._pools = self.get_pools()
        return self._pools

    @property
    def port_ids(self):
        if not self._port_ids:
            self._port_ids = self.get_all_port_ids()
        return self._port_ids

    @property
    def iscsi_port_ids(self):
        if not self._iscsi_port_ids:
            self._iscsi_port_ids = self.get_iscsi_port_ids()
        return self._iscsi_port_ids

    @property
    def fc_port_ids(self):
        if not self._fc_port_ids:
            self._fc_port_ids = self.get_fc_port_ids()
        return self._fc_port_ids

    @property
    def host_groups(self):
        if not self._host_groups:
            self._host_groups = self.get_host_groups()
        return self._host_groups

    ####################################### HELPER METHODS ######################################
    def get_volume_dict(self, name_or_id):
        if not isinstance(name_or_id, str):
            name_or_id = str(name_or_id)

        user_input = name_or_id.strip()
        if user_input.isdigit():
            start = int(user_input) - 1
            for volume in self.get_volumes(headLdevId=start):
                if int(user_input)  == int(volume['ldevId']):
                    self.logger.info(f"\nFound Volume record is: {volume}")
                    return volume
        else:
            for volume in self.get_volumes():
                if 'label' in volume and user_input == volume['label']:
                    self.logger.info(f"\nFound Volume record is: {volume}")
                    return volume

        return {}

    def get_volume_list(self, name:str):
        return [volume  for volume in self.get_volumes() if 'label' in volume and name.strip() == volume['label']]

    def get_host_group_records(self, host_group_name:str):
        return [group for group in self.host_groups if host_group_name == group['hostGroupName']]

    def get_lun_mapping_to_host_group(self, host_group_name):
        hosts = self.get_host_group_records(host_group_name)
        lun_mapping_details = []
        for host in hosts:
            data = self.get_lun_paths(host["portId"], host["hostGroupNumber"])
            lun_mapping_details.extend(data)
        self.logger.info(f"\nLun path to {host_group_name} are {lun_mapping_details}")
        return lun_mapping_details

    def get_host_group_initiators(self, host_group_name):
        hostgroups = []
        for group in self.host_groups:
            if (host_group_name == group['hostGroupName']):
                hostgroups.append(group)

        if not hostgroups:
            self.logger.info(f"\nWe didnt find hostgroup with name {host_group_name}")
            return []

        details = []
        for hostgroup in hostgroups:
            self.logger.info(f"hostgroup = {hostgroup}")
            data = self.get_initiator_from_host_group(hostgroup['portId'], hostgroup['hostGroupName'])
            details.extend(data['data'])
        return details

    def add_host_group(self, host_group_name, connection_option, host_mode="LINUX/IRIX", ports=[]):
        self.logger.info(f"\nChecking if host group name {host_group_name} already exists on hitachi")
        host_group_records = self.get_host_group_records(host_group_name)
        self.logger.info(f"\nExisting host group records with host group name {host_group_name} are:\n  {host_group_records}")

        def get_port_list():
            port_ids = []
            if(len(ports)):
                port_ids.extend(ports)
            else:
                if connection_option.lower() == 'iscsi':
                    port_ids.extend(self.iscsi_port_ids)
                elif connection_option.lower() == 'fc':
                    port_ids.extend(self.fc_port_ids)
            return port_ids

        def get_diff(rec1,rec2):
            return list(set(rec1)-set(rec2))

        add_ports = get_port_list()
        self.logger.info(f"\nWe want these ports in hostgroups:{add_ports}")

        if not host_group_records:
            self.logger.info(f"\nhost group record doesnt exists for {host_group_name} ...so creating hostgroup")
            for port_id in add_ports:
                self.create_host_group(port_id, host_group_name, host_mode)
        else:
            self.logger.info("hostgroup already exist...lets check if it has port and add missing ports if any")
            missing_ports = get_diff(add_ports, [group['portId']  for group in host_group_records])
            for port_id in missing_ports:
                self.logger.info(f"found exisint host group with missing port {port_id} ...adding missing port {port_id}")
                self.create_host_group(port_id, host_group_name, host_mode)

        host_group_records = self.get_host_group_records(host_group_name)
        found_ports = {group['portId']  for group in host_group_records}
        missing  = get_diff(add_ports, found_ports)
        if missing:
            raise RuntimeError(f"failed to create host group with ports {missing}")
        else:
            self.logger.info("now we have host_group with all ports or user provided ports")
        return host_group_records

    def update_host_group_with_initiator(self, host_group_name, initiator_name:str):
        data = self.get_host_group_initiators(host_group_name)
        if data:
            for record in data:
                if record.get('iscsiName') == initiator_name  or record.get('hostWwn') == initiator_name:
                    self.logger.info(f"\nhost group already contain {initiator_name}")
                    continue

                self.logger.info(f"\nadding {initiator_name} to {host_group_name}")
                self.add_initiator_to_host_group(record["portId"], record["hostGroupNumber"], initiator_name)
        else:
            for group in self.get_host_group_records(host_group_name):
                self.logger.info(f"\nadding {initiator_name} to {host_group_name}")
                self.add_initiator_to_host_group(group["portId"], group["hostGroupNumber"], initiator_name)

    def remove_host_group(self,host_group_name):
        data = []
        for group in self.get_host_group_records(host_group_name):
            host_group_id = group['hostGroupId']
            self.logger.info(f"\nremoving {host_group_id} for {host_group_name}")
            data.append(self.delete_host_group(host_group_id))
        return data

    def map_volume_to_host_group(self, host_group_name, volume_name=None):
        self.host_group_volume_operation(host_group_name, volume_name=volume_name, map_to_host=True)

    def unmap_volume_from_host_group(self, host_group_name, volume_name=None):
        self.host_group_volume_operation(host_group_name, volume_name=volume_name, map_to_host=False)

    def get_unused_volume(self):
        volume = None
        while True:
            start = randint(1,16384)
            data = self.get_volumes(ldevOption='undefined',headLdevId=start)
            volume = choice(data)
            self.logger.info(volume)
            with HitachiBoxAPI.lock:
                if volume['ldevId'] not in HitachiBoxAPI.volume_given_for_svol:
                    self.logger.info(f"\nusing {volume['ldevId']} unused volume")
                    HitachiBoxAPI.volume_given_for_svol.add(volume['ldevId'])
                    break
        return volume

    @classmethod
    def get_volumes_given_for_svol(cls):
        with HitachiBoxAPI.lock:
            data = cls.volume_given_for_svol
        return data

    def host_group_volume_operation(self, host_group_name, volume_name=None, map_to_host:bool=True):
        lun_mapping_to_host_group = self.get_lun_mapping_to_host_group(host_group_name)
        volume = self.get_volume_dict(volume_name)
        if not volume:
            raise ValueError(f"Volume '{volume_name}' not found")

        mapping_data = []
        if lun_mapping_to_host_group:
            mapping_data = [data for data in lun_mapping_to_host_group  if data['ldevId'] == volume['ldevId']]
        else:
            self.logger.info(f"\nNo volume mapped to {host_group_name}")

        self.logger.info(f"\nmapping data is {mapping_data}")

        if map_to_host == True:
            if not mapping_data:
                # mapping doesnt exist
                for host in self.get_host_group_records(host_group_name):
                    self.logger.info(f"{volume['ldevId']} is not mapped to {host['portId']}... mapping it")
                    self.create_lun_path(host["portId"], host["hostGroupNumber"], volume['ldevId'])
        else:
            if mapping_data:
                # mapping exist
                for lunMap in mapping_data:
                     lunId = lunMap['lunId']
                     self.logger.info(f"{volume['ldevId']} is mapped to {lunMap['portId']}... unmapping it")
                     self.delete_lun_path(lunMap["portId"], lunMap["hostGroupNumber"], volume['ldevId'], lunId)

    ########## WRAPPER Methods ##############

    def add_cs_host_group(self, host_group_name, initiator_name, connection_option='iscsi', volume_name='GK_CS_HG_creation', ports=[]):
        self.logger.info(f"creating hostgroup {host_group_name} on hitachi")

        data = self.add_host_group(host_group_name=host_group_name ,connection_option=connection_option, ports=ports)

        if initiator_name:
            self.logger.info(f"updating {host_group_name} with {initiator_name}")
            self.update_host_group_with_initiator(host_group_name=host_group_name, initiator_name=initiator_name)


        if initiator_name and volume_name:
            self.logger.info(f"attaching volume {volume_name} to {host_group_name}")
            self.map_volume_to_host_group(host_group_name=host_group_name, volume_name=volume_name )
            return self.get_lun_mapping_to_host_group(host_group_name)
        return self.get_host_group_initiators(host_group_name)

    def remove_cs_host_group(self, host_group_name, volume_name='GK_CS_HG_creation'):
        initiators = self.get_host_group_initiators(host_group_name=host_group_name)

        if initiators and volume_name:
            self.logger.info(f"\nCheck if volume {volume_name} is attached to  {host_group_name} and remove it")
            self.unmap_volume_from_host_group(host_group_name=host_group_name, volume_name=volume_name)

        for initiator in initiators:
            initiator_id = initiator.get('hostIscsiId', None) or initiator.get('hostWwnId', None)
            self.remove_initiator_from_host_group(initiator_id)

        self.logger.info(f"removing hostgroup = {host_group_name}")
        return self.remove_host_group(host_group_name=host_group_name)

    def add_svol(self, primary_vol_id, volume_label=None, volume_prefix="CS_UI_"):
        volume = self.get_unused_volume()
        self.create_svol(primary_vol_id, volume['ldevId'])
        if volume_label:
            volume_name  =  volume_label
        else:
            volume_name = f"svol_{volume['ldevId']}_from_pvol_{primary_vol_id}"

        data = self.add_label_to_volume(volume['ldevId'], volume_name, volume_prefix)
        found = False
        volume_info = None
        while True:
            # wait until volume show up in defined ldevs
            implemented = self.get_volumes(ldevOption='defined',headLdevId=int(volume['ldevId'])-1)
            for x in implemented:
                if x['ldevId'] == int(volume['ldevId']):
                    found = True
                    volume_info = x
                    break
            if found:
                self.logger.info(implemented[0:5])
                self.logger.info("svol added successfully")
                break
            time.sleep(2)
        return volume_info

    def get_secondary_volumes(self):
        secondary_volumes = []
        for volume in self.get_volumes():
            if 'label' in volume and re.search('CS_|Auto_',volume['label']):
                secondary_volumes.append(volume)
        return secondary_volumes

    def remove_volume(self, ldev_id):
        volume =  self.get_volume_dict(ldev_id)
        self.logger.info(volume)
        if volume:
            for port in volume.get('ports',[]):
                lunId=f"{port['portId']},{port['hostGroupNumber']},{port['lun']}"
                self.logger.info(f"\n deleting lun_path forlunid {lunId}")
                self.delete_lun_path(port["portId"], port["hostGroupNumber"], volume['ldevId'], lunId)
            data = self.delete_volume(volume['ldevId'])
            found = False
            final_volume_state = None
            while True:
                # wait until volume show up unimplemeted ldevs

                unimplemented = self.get_volumes(ldevOption='undefined',headLdevId=int(ldev_id)-1)
                for x in unimplemented:
                    if x['ldevId'] == int(ldev_id):
                        found = True
                        final_volume_state = x
                        break

                if found:
                    self.logger.info(unimplemented[0:5])
                    with HitachiBoxAPI.lock:
                        if int(ldev_id) in HitachiBoxAPI.volume_given_for_svol:
                            HitachiBoxAPI.volume_given_for_svol.discard(int(ldev_id))
                    self.logger.info("svol deleted successfully")
                    break
                time.sleep(2)
            return final_volume_state

    ############################################# API ############################################
    def logout(self):
        json = {"force":False}
        if self.sessionid:
            response = self.delete(endpoint=f"/sessions/{self.sessionid}", json=json)
            if response.status_code == 200:
                self.sessionid = None
                self.token = None
                self.session.headers.pop("Authorization", None)
                self.logger.info("Session deleted successfully.")
                return response
            else:
                raise Exception(f"Failed to delete session: {response.status_code} {response.text}")


    def login(self, endpoint,**kwargs):
        """
        Creates a session by sending a POST request with username and password to the API.

        """
        auth = (self.username,  self.password)
        headers = {"accept": "application/json", "Content-Type": "application/json"}
        self.logger.info(self.base_url+endpoint)
        response = self.session.post(url=self.base_url+endpoint, auth=auth, headers=headers, verify=False, **kwargs)

        if response.status_code == 200:
            # Extract session id from the response and store it in the session
            self.sessionid = response.json().get("sessionId", None)
            self.token = response.json().get("token", None)

            if self.sessionid:
                self.session.headers.update({"accept": "application/json",
                                     "Content-Type": "application/json"})
                self.session.headers.update({"Authorization": f"Session {self.token}"})
                self.logger.info("Session created successfully.")
            else:
                self.logger.warn("No sessionid returned in the response.")
        else:
            self.logger.error(f"Failed to create session: {response.status_code} {response.text}")
        return response

    def get_storages(self):
        response = self._request('get','/storages')
        return response.json()['data']

    def get_lun_paths(self, port_id, host_group_number):
        params = {"portId": port_id, "hostGroupNumber": host_group_number}
        response = self._request('get','/luns',params=params)
        data = response.json()['data']
        return data

    def create_lun_path(self, port_id, host_group_number, volume_id):
        data = {"portId": port_id, "hostGroupNumber": host_group_number,"ldevId": volume_id}
        response = self._request('post','/luns', json=data)
        data = response.json()
        self.retrive_job_state(data['jobId'] ,f"mapping {volume_id} to {host_group_number} failed")
        return data

    def delete_lun_path(self, port_id, host_group_number, volume_id, lun_id):
        data = {"portId": port_id, "hostGroupNumber": host_group_number,"ldevId": volume_id}
        response = self._request('delete',f"/luns/{lun_id}", json=data)
        data = response.json()
        self.retrive_job_state(data['jobId'] ,f"unmapping {lun_id} from {host_group_number} failed")
        return data

    def get_ports(self):
        response = self._request('get',"/ports")
        data = response.json()['data']
        return data

    def get_all_port_ids(self):
        data = self.get_ports()
        return [x["portId"] for x in data]

    def get_iscsi_port_ids(self):
        params = {"portType":"ISCSI"}
        response = self._request('get',"/ports", params=params)
        data = response.json()['data']
        return  [x["portId"] for x in data]

    def get_fc_port_ids(self):
        params = {"portType":"FIBRE"}
        response = self._request('get',"/ports", params=params)
        data = response.json()['data']
        return [x["portId"] for x in data]

    def get_pools(self, pool_type=''):
        params={}
        if pool_type.upper() == 'DP':
            params = {"poolType":"DP"}
        elif pool_type.upper() == 'HTI':
            params = {"poolType":"HTI"}

        response = self._request('get',"/pools", params=params)
        data = response.json()['data']
        return data

    def get_host_groups(self, port_id=''):
        params = {}
        if port_id:
            params = {"portId":port_id.upper()}
        response = self._request('get',"/host-groups", params=params, log=False)
        data = response.json()['data']
        return data

    def create_host_group(self, port_id, host_group_name, host_mode="LINUX/IRIX",**optional):
        data = {"portId": port_id, "hostGroupName": host_group_name, "hostMode": host_mode}
        data.update(optional)
        response = self._request('post','/host-groups',json=data)
        data = response.json()
        self.retrive_job_state(data['jobId'],f"creating {host_group_name} failed ")
        self._host_groups = []
        return data


    def remove_initiator_from_host_group(self, host_initiator_id):
        endpoint = ''
        if 'iqn.' in host_initiator_id  or 'eui.' in host_initiator_id:
            endpoint  = f"/host-iscsis/{host_initiator_id}"
        else:
            endpoint =  f"/host-wwns/{host_initiator_id}"

        response = self._request('delete',endpoint)
        data = response.json()
        self.retrive_job_state(data['jobId'],f"updating {host_initiator_id} failed ")
        return data

    def add_initiator_to_host_group(self, port_id, host_group_number, initiator_name):
        endpoint = ''
        data = {"portId": port_id, "hostGroupNumber": host_group_number}
        if initiator_name.startswith('iqn.') or initiator_name.startswith('eui.'):
            endpoint  = "/host-iscsis"
            data["iscsiName"] = initiator_name
        else:
            endpoint =  "/host-wwns"
            data["hostWwn"] = initiator_name

        response = self._request('post',endpoint,json=data)
        data = response.json()
        self.retrive_job_state(data['jobId'],f"updating {host_group_number} failed ")
        return data

    def get_initiator_from_host_group(self, port_id, host_group_name):
        endpoint = ''
        if port_id in self.fc_port_ids:
            self.logger.info("its fc port group")
            endpoint='/host-wwns'
        elif port_id in self.iscsi_port_ids:
            self.logger.info("its iscsiport group")
            endpoint='/host-iscsis'

        if not endpoint:
            raise ValueError(f"Unknown port_id '{port_id}': not found in FC or iSCSI port lists")

        params = {"portId" : port_id, "hostGroupName": host_group_name}

        response = self._request("get", endpoint, params=params)
        data = response.json()
        return data

    def delete_host_group(self, host_group_id):
        response = self._request('delete',endpoint=f"/host-groups/{host_group_id}")
        job_obj=response.json()
        data = self.retrive_job_state(job_obj['jobId'], f"deleting {host_group_id} failed ")
        self._host_groups = []
        return data

    def retrive_job_state(self, job_id, failure_message=''):
        while True:
            response = self._request('get',endpoint=f"/jobs/{job_id}")
            data = response.json()
            if data['status'] == 'Completed':
                break;
            time.sleep(2)

        if(data['state'] != 'Succeeded'):
            raise Exception(f"{failure_message}: {data}")
        return data

    @add_ldev_id_in_hex
    def get_volumes(self, is_labeled=False, **query_params):
        self.logger.info(f"\nFetching Existing Volumes for {query_params} ")
        params = {"ldevOption": "defined"}
        if query_params:
            params.update(query_params)
        result = []
        response = self._request('get',"/ldevs", log=False, params=params)
        result = response.json()['data']
        if not result:
            self.logger.error(f"No data returned from API")
            return []

        last_ldev_id = result[-1].get('ldevId') + 1

        if params.get("ldevOption") == 'defined' and \
           params.get("headLdevId") and \
           params.get("headLdevId") <last_ldev_id :
            return result

        if params.get("ldevOption") == 'undefined':
            if params.get("headLdevId"):
                params.pop("headLdevId", None)
            # returning unimplemented Volumes
            return result

        total = 0
        records_per_page = 100
        while True:
            self.logger.info(f"last_ldev_id = {last_ldev_id }")
            current_records = []
            params['headLdevId'] = last_ldev_id
            response = self._request('get',"/ldevs", params=params, log=False)
            #response = self._request('get', "/ldevs", params={"headLdevId":last_ldev_id}, log=False)
            current_records = response.json()['data']
            if len(current_records):
                last_ldev_id = current_records[-1].get('ldevId', last_ldev_id) + 1
                result.extend(current_records)
            if len(current_records) < records_per_page:
                break;
        if is_labeled:
            filtered_data = [vol for vol in result if 'label' in vol]
            return filtered_data

        return result

    def delete_volume(self, volume_id):
        body = {"isDataReductionDeleteForceExecute": "true"}
        response = self._request('delete',f"/ldevs/{volume_id}", json=body)
        data = response.json()
        final_state = self.retrive_job_state(data['jobId'],f"deleting {volume_id} failed ")
        return final_state


    def create_svol(self, primary_vol_id, unused_secondary_vol_id, is_drs_enabled = True):
        volume = self.get_volume_dict(primary_vol_id)
        if not volume:
            raise ValueError(f"primary volume '{primary_vol_id}' not found")
        body = {"poolId": volume["poolId"],
                "blockCapacity":volume["blockCapacity"],
                "dataReductionMode":"compression_deduplication"
               }
        if unused_secondary_vol_id:
            body["ldevId"] = unused_secondary_vol_id
            body["isDataReductionSharedVolumeEnabled"] = is_drs_enabled

        response = self._request('post',f"/ldevs", json=body)
        data = response.json()
        final_state = self.retrive_job_state(data['jobId'],f"creating svol on {unused_secondary_vol_id} failed ")
        return final_state

    def add_label_to_volume(self,vol_id,label,prefix='CS_UI_'):
         volume = self.get_volume_dict(vol_id)
         if not volume:
            raise ValueError(f"volume '{vol_id}' not found")
         if label:
             body = {"label": prefix + label }
             response = self._request('patch', f"/ldevs/{volume['ldevId']}", json=body)
             data = response.json()
             self.retrive_job_state(data['jobId'],f"adding label {prefix + label} to volume {volume['ldevId']} failed ")
             return data

    ####################################################################################################

if __name__ == '__main__':

    import argparse
    import json

    parser = argparse.ArgumentParser(description="accept SUT, IQN, and optional volume name to create host-group on HitachiBox")
    parser.add_argument("--hitachi-ip", default="10.4.80.144", help="Hitachi storage IP (default: %(default)s)")
    parser.add_argument("--username", default="connector", help="Username (default: %(default)s)")
    parser.add_argument("--password", default="Tw0river", help="Password (default: %(default)s)")
    parser.add_argument("--connection-option", default="iscsi", help="Connection Option can be  fc or iscsi (default: %(default)s)")
    parser.add_argument("--initiator-iqn", help="iSCSI IQN...if not specified it will assume iqn.2003-10.com.indexengines:<sut>")
    parser.add_argument("--discovery-volume-name", default="GK_CS_HG_creation", help="Discovery Volume name for host group creation default: %(default)s)")
    parser.add_argument("--volume-prefix",  help="Volume prefix to be used while creating svol")

    parser.add_argument("--add-host-group", help="host group name")
    parser.add_argument("--remove-host-group", help="host group name")
    parser.add_argument("--remove-svol", help="secondary volume id")
    parser.add_argument("--get-unused-volume", action="store_true", help="Get a unused volume")
    parser.add_argument("--add-svol", action="store_true" ,help="create secondary volume")
    parser.add_argument("--svol-name", help="seconary volume name")
    parser.add_argument("--primary-volume-id", help="primary vol id in decimal")
    parser.add_argument("--get-volume-details", help="get volume details from volume name")


    args = parser.parse_args()
    if args.add_host_group:
        args.initiator_iqn = args.initiator_iqn or f"iqn.2003-10.com.indexengines:{args.add_host_group}"

    hitachi = HitachiBoxAPI(ip=args.hitachi_ip, username=args.username, password=args.password)

    if args.add_host_group:
        print(json.dumps(hitachi.add_cs_host_group(host_group_name=args.add_host_group, initiator_name=args.initiator_iqn, connection_option=args.connection_option, volume_name=args.discovery_volume_name)))
    elif args.remove_host_group:
        print(json.dumps(hitachi.remove_cs_host_group(host_group_name=args.remove_host_group)))
    elif args.get_unused_volume:
        print(json.dumps(hitachi.get_unused_volume()))
    elif args.remove_svol:
        print(json.dumps(hitachi.remove_volume(args.remove_svol)))
    elif args.get_volume_details:
        data = hitachi.get_volume_dict(args.get_volume_details)
        print(json.dumps(data))
    elif args.add_svol:
         if args.primary_volume_id is None:
            parser.error("--create-svol requires --primary-volume-id.")
         optional = {}
         if args.svol_name:
             optional['volume_label'] = args.svol_name
         if args.volume_prefix:
             optional['volume_prefix'] = args.volume_prefix
         print(json.dumps(hitachi.add_svol(args.primary_volume_id, **optional)))
