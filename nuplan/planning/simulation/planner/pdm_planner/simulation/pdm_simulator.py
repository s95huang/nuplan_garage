import numpy as np
import numpy.typing as npt

from nuplan.common.actor_state.ego_state import EgoState
from nuplan.common.actor_state.state_representation import TimePoint

from nuplan.planning.simulation.planner.pdm_planner.simulation.batch_kinematic_bicycle import (
    BatchKinematicBicycleModel,
)
from nuplan.planning.simulation.planner.pdm_planner.simulation.batch_lqr import BatchLQRTracker
from nuplan.planning.simulation.planner.pdm_planner.utils.pdm_array_representation import ego_state_to_state_array

from nuplan.planning.simulation.simulation_time_controller.simulation_iteration import (
    SimulationIteration,
)


class PDMSimulator:
    """
    Re-implementation of nuPlan's simulation pipeline. Enables batch-wise simulation.
    """

    def __init__(self, proposal_samples: int, sample_interval: float):
        """
        Constructor of PDMSimulator.
        :param proposal_samples: number of sample states for the proposal
        :param sample_interval: time interval between samples [s]
        """

        # time parameters
        self._proposal_samples: int = proposal_samples
        self._sample_interval: float = sample_interval

        # simulation objects
        self._motion_model = BatchKinematicBicycleModel()
        self._tracker = BatchLQRTracker()

    def simulate_proposals(
        self, states: npt.NDArray[np.float64], initial_ego_state: EgoState
    ) -> npt.NDArray[np.float64]:
        """_initial_accel_max
        Simulate all proposals over batch-dim
        :param initial_ego_state: ego-vehicle state at current iteration
        :param states: proposal states as array
        :return: simulated proposal states as array
        """

        # TODO: find cleaner way to load parameters
        # set parameters of motion model and tracker
        self._motion_model._vehicle = initial_ego_state.car_footprint.vehicle_parameters
        self._tracker._discretization_time = self._sample_interval
        
        proposal_states = states[:, : self._proposal_samples + 1]
        self._tracker.update(proposal_states)

        # state array representation for simulated vehicle states
        simulated_states = np.zeros(proposal_states.shape, dtype=np.float64)
        simulated_states[:, 0] = ego_state_to_state_array(initial_ego_state)

        # state array representation for simulated vehicle states
        initial_time_point = initial_ego_state.time_point
        simulation_interval_us = int(self._sample_interval * 1e6)
        current_iteration = SimulationIteration(initial_time_point, 0)
        next_iteration = SimulationIteration(
            TimePoint(initial_time_point.time_us + simulation_interval_us), 1
        )
        
        for time_idx in range(1, self._proposal_samples + 1):
            sampling_time: TimePoint = next_iteration.time_point - current_iteration.time_point
            
            command_states = self._tracker.track_trajectory(
                current_iteration,
                next_iteration,
                simulated_states[:, time_idx - 1],
            )

            simulated_states[:, time_idx] = self._motion_model.propagate_state(
                states=simulated_states[:, time_idx - 1],
                command_states=command_states,
                sampling_time=sampling_time,
            )

            current_iteration = next_iteration
            next_iteration = SimulationIteration(
                TimePoint(current_iteration.time_us + simulation_interval_us), 1 + time_idx
            )

        return simulated_states