Mi Band 4 – BLE Test Suite & Discovery Tool

Este diretório contém uma ferramenta de testes e exploração Bluetooth Low Energy (BLE) para a Xiaomi Mi Band 4, desenvolvida como parte de um projeto maior de monitoramento de saúde contínuo (24/7) usando Raspberry Pi.

O objetivo deste script não é monitorar, mas entender profundamente como a Mi Band 4 se comporta no BLE.

🎯 Objetivo da Ferramenta

O miband4_test_suite.py foi criado para:

Descobrir todos os serviços BLE expostos pela Mi Band 4

Listar todas as characteristics, com permissões reais

Testar:

leitura (read)

notificações (notify)

escrita (write)

Validar quais UUIDs realmente funcionam

Coletar dados brutos para engenharia reversa

Evitar suposições baseadas em documentação incompleta da internet

👉 Tudo aqui é baseado em observação prática, não achismo.

🧠 Para quem é este script?

Este script é útil para:

Desenvolvedores Python

Pessoas estudando BLE na prática

Entusiastas de IoT e wearables

Quem quer criar projetos próprios com Mi Band

Quem quer entender por que alguns UUIDs funcionam e outros não

Não é necessário ser especialista em BLE para rodar — apenas curiosidade.

🧰 O que o script faz (em alto nível)

Ao ser executado, o script:

Conecta à Mi Band 4 via BLE

Autentica usando Auth Key real

Descobre todos os serviços BLE

Lista characteristics e permissões

Tenta:

ler dados

ativar notificações

Testa especificamente:

batimento cardíaco

bateria

Escuta notificações por um período

Exibe tudo com timestamp completo

🔐 Autenticação (Importante)

A Mi Band 4 não libera dados sensíveis sem autenticação.

Este script implementa o fluxo real:

Envia pedido de challenge

Recebe challenge via notify

Responde usando AES (Auth Key)

Só então ativa serviços como:

batimento cardíaco

bateria

serviços Xiaomi proprietários

Sem isso, vários UUIDs retornam vazio ou erro.

❤️ Batimento Cardíaco (Heart Rate)

O script identifica e testa:

Serviço BLE padrão de Heart Rate

Characteristic de controle

Characteristic de medição via notify

Exemplo real de dados recebidos:

004c → 76 BPM
0047 → 71 BPM
004f → 79 BPM


📌 O segundo byte representa o BPM.

🔋 Bateria (Descoberta Importante)

Durante os testes, foi confirmado que:

❌ O UUID padrão BLE de bateria não existe na Mi Band 4

✅ A bateria está disponível via UUID proprietário Xiaomi

O script testa automaticamente os UUIDs conhecidos e registra:

sucesso

falha

payload bruto

Isso evita erros comuns em projetos BLE.

⚠️ Erros Esperados (e normais)

Durante a execução, você verá mensagens como:

Read not permitted

Notify acquired

Characteristic not found

Multiple Characteristics with this UUID

Isso não é bug.

São proteções normais do BLE e da Mi Band, e o script:

captura

registra

segue em frente

👉 O objetivo é mapear o comportamento, não forçar acesso.

🖥️ Requisitos

Linux (testado em Raspberry Pi OS)

Python 3.9+

Bluetooth funcionando (BlueZ)

Ambiente virtual com:

bleak

pycryptodome

▶️ Como executar

Ative o ambiente virtual:

source ~/bluetooth/miband/bin/activate


Execute o teste:

python versions/tools/miband4_test_suite.py


O script roda por alguns minutos, coleta dados e encerra sozinho.

📄 Saída do Script

A saída é totalmente em texto, com timestamps completos:

serviços descobertos

UUIDs

leituras bem-sucedidas

erros esperados

notificações recebidas

Esse log é ideal para:

análise

documentação

escrita de artigos

base para novos scripts

📌 Importante

Este script não deve rodar ao mesmo tempo que:

monitoramento contínuo

scripts de alertas

qualquer outro cliente BLE conectado à Mi Band

A Mi Band não suporta múltiplas conexões BLE simultâneas.

🚀 Próximos Passos

Este test suite serve como base para:

documentação técnica

artigos educacionais

melhoria do monitoramento 24/7

expansão para outros wearables

❤️ Por que isso existe?

Este projeto nasceu de uma motivação real:
usar tecnologia para cuidar melhor de quem a gente ama.

Antes de construir alertas, relatórios e lógica de saúde,
foi necessário entender o dispositivo de verdade.

Este script é essa fundação.
