from typing import Any

from controlserver.models import Service
from controlserver.scoring.algorithms.algorithm import ScoreTickAlgorithm
from controlserver.scoring.algorithms.firstblood import FirstBloodAlgorithm
from controlserver.utils.import_factory import ImportFactory
from saarctf_commons.config import ScoringConfig


class ScoreAlgorithmFactory(ImportFactory[ScoreTickAlgorithm]):
    base_class = ScoreTickAlgorithm

    @classmethod
    def build(cls, config: ScoringConfig, team_ids: list[int], services: list[Service], **kwargs: Any) -> ScoreTickAlgorithm:
        return cls.get_class(config.algorithm)(config, team_ids, services, **kwargs)


class FirstBloodAlgorithmFactory(ImportFactory[FirstBloodAlgorithm]):
    base_class = FirstBloodAlgorithm

    @classmethod
    def build(cls, config: ScoringConfig, services: list[Service], **kwargs: Any) -> FirstBloodAlgorithm:
        return cls.get_class(config.firstblood_algorithm)(config, services, **kwargs)
