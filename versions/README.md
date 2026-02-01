## Versões do projeto

Este projeto evoluiu de forma incremental, sempre priorizando
estabilidade, confiabilidade e redução de falsos positivos.

### v1_basic_hr.py
- Leitura básica de batimento cardíaco (BPM)
- Prova de conceito de conexão BLE com a Mi Band 4

---

### v2_reconnect.py
- Monitoramento contínuo (24/7)
- Reconexão automática em caso de queda BLE
- Base para funcionamento prolongado

---

### v5_alerts.py
- Monitoramento contínuo de batimentos cardíacos
- Alertas automáticos para:
  - Bradicardia
  - Taquicardia
  - Ausência de dados por período prolongado
- Notificações via ntfy (push no celular)
- Persistência de dados em SQLite

---

### v6_state.py
- Inclui tudo do `v5_alerts`
- Introduz **estado do wearable**, inferido por dados reais:
  - `IN_USE` → pulseira no pulso
  - `CHARGING` → pulseira no carregador
  - `REMOVED` → pulseira fora do pulso
- Evita falsos alertas durante carregamento
- Registra eventos de colocação e remoção da pulseira

---

### v7_reconnect (família v7_reconnect_*)
- Reestrutura completa da lógica de reconexão BLE
- Foco em **estabilidade após afastamento físico** da Raspberry Pi
- Trata cenários reais:
  - usuário sai de casa com a pulseira
  - conexão BLE é perdida
  - retorno posterior sem necessidade de reiniciar o script
- Evita loops infinitos de reconexão
- Reconexão baseada em:
  - atividade real (batimento cardíaco)
  - estado da conexão BLE
- Isola falhas de leitura (ex: bateria) sem derrubar o monitoramento

> A versão v7 marca a transição do projeto de um monitor funcional
> para um sistema **robusto o suficiente para uso contínuo no mundo real**.
