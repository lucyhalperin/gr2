import numpy as np
import time

from maci.misc import logger
from copy import deepcopy


def rollout(env, policy, path_length, render=False, speedup=None):
    Da = env.action_space.flat_dim
    Do = env.observation_space.flat_dim

    observation = env.reset()
    policy.reset()

    observations = np.zeros((path_length + 1, Do))
    actions = np.zeros((path_length, Da))
    terminals = np.zeros((path_length, ))
    rewards = np.zeros((path_length, ))
    agent_infos = []
    env_infos = []

    t = 0
    for t in range(path_length):

        action, agent_info = policy.get_action(observation)
        next_obs, reward, terminal, env_info = env.step(action)

        agent_infos.append(agent_info)
        env_infos.append(env_info)

        actions[t] = action
        terminals[t] = terminal
        rewards[t] = reward
        observations[t] = observation

        observation = next_obs

        if render:
            env.render()
            time_step = 0.05
            time.sleep(time_step / speedup)

        if terminal:
            break

    observations[t + 1] = observation

    path = {
        'observations': observations[:t + 1],
        'actions': actions[:t + 1],
        'rewards': rewards[:t + 1],
        'terminals': terminals[:t + 1],
        'next_observations': observations[1:t + 2],
        'agent_infos': agent_infos,
        'env_infos': env_infos
    }

    return path


def rollouts(env, policy, path_length, n_paths):
    paths = [
        rollout(env, policy, path_length)
        for i in range(n_paths)
    ]

    return paths


class Sampler(object):
    def __init__(self, max_path_length, min_pool_size, batch_size):
        self._max_path_length = max_path_length
        self._min_pool_size = min_pool_size
        self._batch_size = batch_size

        self.env = None
        self.policy = None
        self.pool = None

    def initialize(self, env, policy, pool):
        self.env = env
        self.policy = policy
        self.pool = pool

    def set_policy(self, policy):
        self.policy = policy

    def sample(self):
        raise NotImplementedError

    def batch_ready(self):
        enough_samples = self.pool.size >= self._min_pool_size
        return enough_samples

    def random_batch(self):
        return self.pool.random_batch(self._batch_size)

    def terminate(self):
        self.env.terminate()

    def log_diagnostics(self):
        logger.record_tabular('pool-size', self.pool.size)


class SimpleSampler(Sampler):
    def __init__(self, **kwargs):
        super(SimpleSampler, self).__init__(**kwargs)

        self._path_length = 0
        self._path_return = 0
        self._last_path_return = 0
        self._max_path_return = -np.inf
        self._n_episodes = 0
        self._current_observation = None
        self._total_samples = 0

    def sample(self):
        if self._current_observation is None:
            self._current_observation = self.env.reset()

        action, _ = self.policy.get_action(self._current_observation)
        next_observation, reward, terminal, info = self.env.step(action)
        self._path_length += 1
        self._path_return += reward
        self._total_samples += 1

        self.pool.add_sample(
            observation=self._current_observation,
            action=action,
            reward=reward,
            terminal=terminal,
            next_observation=next_observation)

        if terminal or self._path_length >= self._max_path_length:
            self.policy.reset()
            self._current_observation = self.env.reset()
            self._path_length = 0
            self._max_path_return = max(self._max_path_return,
                                        self._path_return)
            self._last_path_return = self._path_return

            self._path_return = 0
            self._n_episodes += 1

        else:
            self._current_observation = next_observation

    def log_diagnostics(self):
        super(SimpleSampler, self).log_diagnostics()

        logger.record_tabular('max-path-return', self._max_path_return)
        logger.record_tabular('last-path-return', self._last_path_return)
        logger.record_tabular('episodes', self._n_episodes)
        logger.record_tabular('total-samples', self._total_samples)


class MASampler(SimpleSampler):
    def __init__(self, tb_writer,agent_num, joint, **kwargs):
        super(SimpleSampler, self).__init__(**kwargs)
        self.agent_num = agent_num
        self.joint = joint
        self._path_length = 0
        self._path_return = np.array([0.] * self.agent_num, dtype=np.float32)
        self._last_path_return = np.array([0.] * self.agent_num, dtype=np.float32)
        self._max_path_return = np.array([-np.inf] * self.agent_num, dtype=np.float32)
        self._n_episodes = 0
        self._total_samples = 0
        self._tb_writer = tb_writer

        self._current_observation_n = None
        self.env = None
        self.agents = None

    def set_policy(self, policies):
        for agent, policy in zip(self.agents, policies):
            agent.policy = policy

    def batch_ready(self):
        enough_samples = self.agents[0].pool.size >= self._min_pool_size
        return enough_samples

    def random_batch(self, i):
        return self.agents[i].pool.random_batch(self._batch_size)

    def initialize(self, env, agents):
        self._current_observation_n = None
        self.env = env
        self.agents = agents

    def sample(self):
        if self._current_observation_n is None:
            self._current_observation_n = self.env.reset()
        action_n = []
        for agent, current_observation in zip(self.agents, self._current_observation_n):
            action, _ = agent.policy.get_action(current_observation,self._n_episodes)
            if agent.joint_policy:
                action_n.append(np.array(action)[0:agent._action_dim])
            else:
                action_n.append(np.array(action))

        next_observation_n, reward_n, done_n, info = self.env.step(action_n)  ## printing action! 
        #if self._total_samples > 100000:
        #    self.env.render()

        self._path_length += 1
        #if self._total_samples > 13775:
        #    print(action_n,reward_n)
        self._path_return += np.array(reward_n, dtype=np.float32)
        self._total_samples += 1

        for i, agent in enumerate(self.agents):
            action = deepcopy(action_n[i])
            if agent.pool.joint:
                opponent_action = deepcopy(action_n)
                del opponent_action[i]
                opponent_action = np.array(opponent_action).flatten()
                agent.pool.add_sample(observation=self._current_observation_n[i],
                                      action=action,
                                      reward=reward_n[i],
                                      terminal=done_n[i],
                                      next_observation=next_observation_n[i],
                                      opponent_action=opponent_action)
            else:
                agent.pool.add_sample(observation=self._current_observation_n[i],
                                      action=action,
                                      reward=reward_n[i],
                                      terminal=done_n[i],
                                      next_observation=next_observation_n[i])
        
        if np.all(done_n) or self._path_length >= self._max_path_length:
            self._current_observation_n = self.env.reset()
            self._max_path_return = np.maximum(self._max_path_return, self._path_return)
            self._mean_path_return = self._path_return / self._path_length
            self._last_path_return = self._path_return

            self._path_length = 0

            self._path_return = np.array([0.] * self.agent_num, dtype=np.float32)
            self._n_episodes += 1

            self.log_diagnostics()
            logger.dump_tabular(with_prefix=False)

        else:
            self._current_observation_n = next_observation_n

    def log_diagnostics(self):
        for i in range(self.agent_num):
            self._tb_writer.add_scalars("Last_return",{"Agent" + str(i): self._last_path_return[i]}, self._total_samples)
            if np.isnan(self._max_path_return[i]):
                print(5/0)
            logger.record_tabular('max-path-return_agent_{}'.format(i), self._max_path_return[i])
            logger.record_tabular('mean-path-return_agent_{}'.format(i), self._mean_path_return[i])
            logger.record_tabular('last-path-return_agent_{}'.format(i), self._last_path_return[i])
        logger.record_tabular('episodes', self._n_episodes)
        logger.record_tabular('total-samples', self._total_samples)



class DummySampler(Sampler):
    def __init__(self, batch_size, max_path_length):
        super(DummySampler, self).__init__(
            max_path_length=max_path_length,
            min_pool_size=0,
            batch_size=batch_size)

    def sample(self):
        pass
