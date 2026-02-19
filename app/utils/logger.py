"""
Logger estruturado para toda a aplicação.

Usa Python logging padrão com formatação legível e consistente.
Em produção, pode ser substituído por loguru, structlog ou Cloud Logging.

Decisão técnica: logging padrão para não adicionar dependências desnecessárias.
A padronização de format facilita integração com ferramentas de observabilidade.
"""

import logging
import sys
from typing import Optional


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """
    Retorna um logger configurado para o módulo especificado.

    Cada módulo deve chamar get_logger(__name__) para identificar
    a origem do log nos registros.
    """
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados se o logger já foi configurado
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        # Evita propagação para o root logger (evita logs duplicados)
        logger.propagate = False

    return logger
