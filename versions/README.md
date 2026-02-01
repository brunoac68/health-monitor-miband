# Health Monitor - Mi Band 4

## Versões

- v1_basic_hr.py
  Leitura básica de BPM (prova de conceito)

- v2_reconnect.py
  Monitor 24/7 com reconexão automática

## Arquivo ativo
- current.py → aponta para a versão em uso

## Objetivo
Monitorar sinais vitais de idoso com alertas locais e remotos.

## v5_alerts.py
- Monitoramento de batimentos cardíacos
- Alertas de bradicardia, taquicardia e ausência de dados
- Notificações via ntfy
- Dados persistidos em SQLite

## v6_state.py
- Tudo da v5_alerts
- Introduz estado do wearable:
  - IN_USE
  - CHARGING
  - REMOVED
- Evita falso alerta durante carregamento
- Registra eventos de colocação/remoção do carregador
