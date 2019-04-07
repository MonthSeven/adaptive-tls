import os
import sys
import numpy as np

from .processing import network_utils
from .simulation.collaborator import Collaborator
from .additional.induction_loops import process_additional_file

from gym import spaces
from ray.rllib.env.multi_agent_env import MultiAgentEnv

if 'SUMO_HOME' in os.environ:
    tools = os.path.join(os.environ['SUMO_HOME'], 'tools')
    sys.path.append(tools)
else:
    sys.exit("Please declare environment variable 'SUMO_HOME'")

import tools.sumolib as sumolib
import tools.traci as traci

_PROBLEMATIC_TRAFFICLIGHTS = [
    'cluster_290051912_298136030_648538909',
    'cluster_2511020102_2511020103_290051922_298135886',
]


class Env(MultiAgentEnv):
    r"""SUMO Environment for Adaptive Traffic Light Control.

    Arguments:
        net_file (str): SUMO .net.xml file.
        config_file (str): SUMO .config file.
        additional_file (str): SUMO .det.xml file.
        use_gui (bool): whether to run SUMO simulation with GUI visualisation.
        single_agent (bool): whether the environment is single or multi agent.
    """

    def __init__(self, net_file, config_file, additional_file, use_gui=True, single_agent=True):
        self.trafficlight_skeletons = {}
        self.trafficlight_ids = []
        self.action_space = None
        self.observation_space = None
        self.collaborator = None

        net = sumolib.net.readNet(net_file)

        # Preprocess the network definition and produce internal representation of each trafficlight
        for trafficlight in net.getTrafficLights():
            id_ = trafficlight.getID()
            if id_ in _PROBLEMATIC_TRAFFICLIGHTS: continue

            self.trafficlight_skeletons[id_] = network_utils.extract_tl_skeleton(net, trafficlight)
            self.trafficlight_ids.append(id_)

        # Preprocess the file with information about induction loops
        self.additional = process_additional_file(additional_file)

        # Define the command to run SUMO simulation
        if use_gui:
            sumo_binary = sumolib.checkBinary('sumo-gui')
        else:
            sumo_binary = sumolib.checkBinary('sumo')
        self._sumo_cmd = [sumo_binary, '--start', '--quit-on-end', '-c', config_file]

        self.observation_space = spaces.Box(low=0.0, high=1.0,
                                            shape=Collaborator.get_observation_space_shape(), dtype=np.float32)
        self.action_space = spaces.Discrete(Collaborator.get_action_space_shape())

    def step(self, actions):
        return self.collaborator.step(actions)

    def reset(self):
        traci.start(self._sumo_cmd)

        # Reinitialize the collaborator since the connection changed
        self.collaborator = Collaborator(traci.getConnection(), self.trafficlight_skeletons, self.additional)
        return self.collaborator.compute_observations()

    def close(self):
        traci.close()
        self.collaborator = None