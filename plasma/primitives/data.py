import numpy as np
import time
import sys,os

from scipy.interpolate import UnivariateSpline

from plasma.utils.processing import get_individual_shot_file
from plasma.utils.downloading import format_save_path,get_missing_value_array

# class SignalCollection:
#   """GA Data Obj"""
#   def __init__(self,signal_descriptions,signal_paths):
#       self.signals = []
#       for i in range(len(signal_paths))
#           self.signals.append(Signal(signal_descriptions[i],signal_paths[i]))

class Signal(object):
    def __init__(self,description,paths,machines,tex_label=None,
        causal_shifts=None,is_ip=False,normalize=True,
        data_avail_tolerances=None,is_strictly_positive=False,
        mapping_paths=None):
        assert(len(paths) == len(machines))
        self.description = description
        self.paths = paths
        self.machines = machines #on which machines is the signal defined
        if causal_shifts == None:
            causal_shifts = [0 for m in machines]
        self.causal_shifts = causal_shifts #causal shift in ms
        self.is_ip = is_ip
        self.num_channels = 1
        self.normalize = normalize
        if data_avail_tolerances == None:
            data_avail_tolerances = [0 for m in machines]
        self.data_avail_tolerances = data_avail_tolerances
        self.is_strictly_positive=is_strictly_positive
        self.mapping_paths = mapping_paths

    def is_strictly_positive_fn(self):
        return self.is_strictly_positive

    def is_ip(self):
        return self.is_ip

    def get_file_path(self,prepath,machine,shot_number):
        dirname = self.get_path(machine)
        return get_individual_shot_file(prepath + '/' + machine.name + '/' +dirname + '/',shot_number)

    def is_valid(self,prepath,shot,dtype='float32'):
        t,data,exists = self.load_data(prepath,shot,dtype)
        return exists 

    def is_saved(self,prepath,shot):
        file_path = self.get_file_path(prepath,shot.machine,shot.number)
        return os.path.isfile(file_path)

    def load_data_from_txt_safe(self,prepath,shot,dtype='float32'):
        file_path = self.get_file_path(prepath,shot.machine,shot.number)
        if not self.is_saved(prepath,shot):
            print('Signal {}, shot {} was never downloaded'.format(self.description,shot.number))
            return None,False

        if os.path.getsize(file_path) == 0:
            print('Signal {}, shot {} was downloaded incorrectly (empty file). Removing.'.format(self.description,shot.number))
            os.remove(file_path)
            return None,False
        try:
            data = np.loadtxt(file_path,dtype=dtype)
            if data == get_missing_value_array():
                print('Signal {}, shot {} contains no data'.format(self.description,shot.number))
                return None,False
        except:
            print('Couldnt load signal {} shot {}. Removing.'.format(file_path,shot.number))
            os.remove(file_path)
            return None, False


        return data,True

    def load_data(self,prepath,shot,dtype='float32'):
        data,succ = self.load_data_from_txt_safe(prepath,shot)
        if not succ:
            return None,None,False
            
        if np.ndim(data) == 1:
            data = np.expand_dims(data,axis=0)

        t = data[:,0]
        sig = data[:,1:]

        if self.is_ip: #restrict shot to current threshold
            region = np.where(np.abs(sig) >= shot.machine.current_threshold)[0]
            if len(region) == 0:
                print('shot {} has no current'.format(shot.number))
                return None,None,False
            first_idx = region[0]
            last_idx = region[-1]
            last_time = t[last_idx]+5e-2 #add 50 ms to cover possible disruption event
            last_indices = np.where(t > last_time)[0]
            if len(last_indices) == 0:
                last_idx = -1
            else:
                last_idx = last_indices[0]
            t = t[first_idx:last_idx]
            sig = sig[first_idx:last_idx,:]

        #make sure shot is not garbage data
        if len(t) <= 1 or (np.max(sig) == 0.0 and np.min(sig) == 0.0):
            if self.is_ip:
                print('shot {} has no current'.format(shot.number))
            else:
                print('Signal {}, shot {} contains no data'.format(self.description,shot.number))
            return None,None,False
        
        #make sure data doesn't contain nan
        if np.any(np.isnan(t)) or np.any(np.isnan(sig)):
            print('Signal {}, shot {} contains NAN'.format(self.description,shot.number))
            return None,None,False

        return t,sig,True

    def is_defined_on_machine(self,machine):
        return machine in self.machines

    def is_defined_on_machines(self,machines):
        return all([m in self.machines for m in machines])

    def get_path(self,machine):
        idx = self.get_idx(machine)
        return self.paths[idx]

    def get_mapping_path(self,machine):
        if self.mapping_paths is None:
            return None
        else:
            idx = self.get_idx(machine)
            return self.mapping_paths[idx]    

    def get_causal_shift(self,machine):
        idx = self.get_idx(machine)
        return self.causal_shifts[idx]

    def get_data_avail_tolerance(self,machine):
        idx = self.get_idx(machine)
        return self.data_avail_tolerances[idx]

    def get_idx(self,machine):
        assert(machine in self.machines)
        idx = self.machines.index(machine)  
        return idx

    def __eq__(self,other):
        if other is None:
            return False
        return self.description.__eq__(other.description)

    
    def __ne__(self,other):
        return self.description.__ne__(other.description)

    def __lt__(self,other):
        return self.description.__lt__(other.description)
    
    def __hash__(self):
        return self.description.__hash__()

    def __str__(self):
        return self.description
    
    def __repr__(self):
        return self.description

class ProfileSignal(Signal):
    def __init__(self,description,paths,machines,tex_label=None,causal_shifts=None,mapping_range=(0,1),num_channels=32,data_avail_tolerances=None,is_strictly_positive=False,mapping_paths=None):
        super(ProfileSignal, self).__init__(description,paths,machines,tex_label,causal_shifts,is_ip=False,data_avail_tolerances=data_avail_tolerances,is_strictly_positive=is_strictly_positive,mapping_paths=mapping_paths)
        self.mapping_range = mapping_range
        self.num_channels = num_channels

    def load_data(self,prepath,shot,dtype='float32'):
        data,succ = self.load_data_from_txt_safe(prepath,shot)
        if not succ:
            return None,None,False

        if np.ndim(data) == 1:
            data = np.expand_dims(data,axis=0)
            #_ = data[0,0]
        T = data.shape[0]/2 #time is stored twice, once for mapping and once for signal
        mapping = data[:T,1:]
        remapping = np.linspace(self.mapping_range[0],self.mapping_range[1],self.num_channels)
        t = data[:T,0] 
        sig = data[T:,1:]
        if sig.shape[1] < 2:
            print('Signal {}, shot {} should be profile but has only one channel. Possibly only one profile fit was run for the duration of the shot and was transposed during downloading. Need at least 2.'.format(self.description,shot.number))
            return None,None,False
        if len(t) <= 1 or (np.max(sig) == 0.0 and np.min(sig) == 0.0):
            print('Signal {}, shot {} contains no data'.format(self.description,shot.number))
            return None,None,False
        if np.any(np.isnan(t)) or np.any(np.isnan(sig)):
            print('Signal {}, shot {} contains NAN'.format(self.description,shot.number))
            return None,None,False

        timesteps = len(t)
        sig_interp = np.zeros((timesteps,self.num_channels))
        for i in range(timesteps):
            f = UnivariateSpline(mapping[i,:],sig[i,:],s=0,k=1,ext=0)
            sig_interp[i,:] = f(remapping)

        return t,sig_interp,True


class Machine(object):
    def __init__(self,name,server,fetch_data_fn,max_cores = 8,current_threshold=0):
        self.name = name
        self.server = server
        self.max_cores = max_cores
        self.fetch_data_fn = fetch_data_fn
        self.current_threshold = current_threshold

    def get_connection(self):
        return Connection(server)

    def fetch_data(self,signal,shot_num,c):
        path = signal.get_path(self)
        mapping_path = signal.get_mapping_path(self)
        success = False
        mapping = None
        try:
            time,data,mapping,success = self.fetch_data_fn(path,shot_num,c)
            if mapping is not None and np.ndim(mapping) == 1:#make sure there is a mapping for every timestep
                T = len(time)
                mapping = np.tile(mapping,(T,1)).transpose()
                assert(mapping.shape == data.shape), "shape of mapping and data is different"
            if mapping_path is not None:#fetch the mapping separately
                time_map,data_map,mapping_map,success_map = self.fetch_data_fn(mapping_path,shot_num,c)
                success = (success and success_map)
                if not success:
                    print("No success for signal {} and mapping {}".format(path,mapping_path))
                else:
               	    assert(np.all(time == time_map)), "time for signal {} and mapping {} don't align: \n{}\n\n{}\n".format(path,mapping_path,time,time_map)
                    mapping = data_map
        except Exception as e:
            print(e)
            sys.stdout.flush()

        if not success:
            return None,None,None,False

        time = np.array(time) + 1e-3*signal.get_causal_shift(self)
        return time,np.array(data),mapping,success

    def __eq__(self,other):
        return self.name.__eq__(other.name)

    def __lt__(self,other):
        return self.name.__lt__(other.name)
    
    def __ne__(self,other):
        return self.name.__ne__(other.name)
    
    def __hash__(self):
        return self.name.__hash__()
    
    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()


