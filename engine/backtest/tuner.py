"""Reusable RL hyperparameter tuner (linear Q-learning).

Ported from the crypto (rl-agent-swarm) `rl/q_learning_agent.py` +
`agents/rl_tuner.py` into a single generic, dependency-light class so any
vertical's backtest/paper loop can dynamically tune a strategy's numeric
parameters online.

`Q(s, a) = w_a^T . s_augmented` with SGD TD-error updates. The tuner wraps a
"strategy" object whose tunable attributes are adjusted (increase / decrease /
hold) each step, rewarded by realised PnL.

`numpy` is imported lazily inside methods so `import engine.backtest.tuner`
succeeds even in an environment without numpy.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class QLearningAgent:
    """Linear-function-approximation Q-learning agent (numpy only)."""

    def __init__(self, state_size: int = 10, action_size: int = 3,
                 learning_rate: float = 0.01, gamma: float = 0.95,
                 epsilon: float = 1.0, epsilon_decay: float = 0.995,
                 epsilon_min: float = 0.01):
        import numpy as np
        self.state_size = state_size
        self.action_size = action_size
        self.learning_rate = learning_rate
        self.gamma = gamma
        self.epsilon = epsilon
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        # +1 column for the bias term.
        self.weights = np.random.uniform(-0.1, 0.1, (action_size, state_size + 1))
        self.training_steps = 0
        self.accumulated_loss = 0.0

    def _add_bias(self, state):
        import numpy as np
        state = np.asarray(state, dtype=float)
        if state.ndim == 1:
            return np.append(state, 1.0)
        return np.hstack((state, np.ones((state.shape[0], 1))))

    def get_q_values(self, state):
        import numpy as np
        return np.dot(self.weights, self._add_bias(state))

    def select_action(self, state, training: bool = True) -> int:
        import numpy as np
        if training and np.random.random() < self.epsilon:
            return int(np.random.randint(self.action_size))
        return int(np.argmax(self.get_q_values(state)))

    def learn(self, state, action: int, reward: float, next_state, done: bool) -> float:
        import numpy as np
        state_aug = self._add_bias(state)
        current_q = float(np.dot(self.weights[action], state_aug))
        if done:
            target_q = reward
        else:
            target_q = reward + self.gamma * float(np.max(self.get_q_values(next_state)))
        td_error = target_q - current_q
        self.weights[action] += self.learning_rate * td_error * state_aug
        self.training_steps += 1
        self.accumulated_loss += td_error ** 2
        if self.epsilon > self.epsilon_min:
            self.epsilon *= self.epsilon_decay
        return td_error ** 2


class RLHyperparameterTuner:
    """Q-learning wrapper that tunes a strategy object's numeric attributes.

    Args:
        strategy: any object with the tunable attributes as instance attributes.
        config: dict with a ``tunable_params`` mapping
            ``{name: {"min": .., "max": .., "step": ..}}`` and optional
            ``state_size``, ``learning_rate``, ``gamma``, ``epsilon``.

    Action space: for N tunable params -> 2N+1 actions
    (increase i, decrease i, or hold-all).
    """

    def __init__(self, strategy: Any, config: Dict[str, Any]):
        self.strategy = strategy
        self.config = config
        self.param_config: Dict[str, Dict[str, float]] = config.get("tunable_params", {})
        self.param_names: List[str] = list(self.param_config.keys())
        self.n_params = len(self.param_names)
        self.action_size = 2 * self.n_params + 1

        self.rl_agent = QLearningAgent(
            state_size=config.get("state_size", 10),
            action_size=max(self.action_size, 1),
            learning_rate=config.get("learning_rate", 0.01),
            gamma=config.get("gamma", 0.95),
            epsilon=config.get("epsilon", 1.0),
        )
        self.last_state = None
        self.last_action = None

    def update_parameters(self, state) -> Dict[str, Any]:
        """Pick an action for `state` and apply it to the strategy attributes."""
        if self.n_params == 0:
            return {}
        action = self.rl_agent.select_action(state)
        self.last_state = state
        self.last_action = action

        if action == 2 * self.n_params:  # hold-all
            return self._current_params()

        param_idx = action % self.n_params
        is_increase = action < self.n_params
        name = self.param_names[param_idx]
        limits = self.param_config[name]
        step = limits["step"]
        current = getattr(self.strategy, name, 0)
        if is_increase:
            new_val = min(current + step, limits["max"])
        else:
            new_val = max(current - step, limits["min"])
        setattr(self.strategy, name, new_val)
        return self._current_params()

    def learn(self, reward: float, next_state, done: bool) -> None:
        if self.last_state is not None and self.last_action is not None:
            self.rl_agent.learn(self.last_state, self.last_action, reward, next_state, done)

    def _current_params(self) -> Dict[str, Any]:
        return {name: getattr(self.strategy, name, None) for name in self.param_names}

    # Public alias kept stable for callers.
    def current_params(self) -> Dict[str, Any]:
        return self._current_params()
