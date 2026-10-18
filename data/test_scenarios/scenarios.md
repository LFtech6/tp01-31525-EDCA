# Catálogo de cenários de teste (etiquetas definidas à priori)

Gerado por `data/generator/generate_events.py` (semente fixa). As etiquetas foram definidas a partir do contexto de cada cenário, **antes** e **independentemente** do motor de regras.

| ID | Suspeito | Risco esperado | Cenário | Justificação |
|---|---|---|---|---|
| S01 | sim | HIGH | Intrusão noturna no laboratório | Utilizador sem permissão para Z03 tenta entrar às 02:13 (recusado) e há movimento dentro da zona 1 minuto depois: alguém entrou por outra via ou forçou a porta. |
| S02 | sim | HIGH | Tentativas repetidas na sala de servidores | Quatro recusas em menos de 3 minutos na porta da zona CRITICAL por um utilizador sem permissão: padrão de tentativa de acesso forçado ou cartão clonado. |
| S03 | sim | HIGH | Acesso concedido sem permissão a zona crítica | Prestador externo (U045) recebe acesso à sala de servidores, para a qual não tem permissão; seguido de movimento. Indica erro de configuração do controlador ou cartão adulterado. |
| S04 | sim | MEDIUM | Movimento noturno no arquivo sem qualquer acesso | Três deteções de movimento no arquivo (RESTRICTED) às 03:40, zona fechada, sem nenhum registo de acesso: presença não autorizada. |
| S05 | sim | MEDIUM | Ex-colaborador a tentar entrar | Utilizador inativo (U044) tenta entrar duas vezes nos escritórios antes da abertura: credencial que devia estar revogada. |
| S06 | sim | HIGH | Tailgating na sala de servidores | Utilizador sem permissão (U024) é recusado e, 30 s depois, um administrador entra; a porta abre duas vezes e há movimento: o recusado entrou à boleia. |
| S07 | sim | MEDIUM | Acesso noturno ao laboratório fora do horário do utilizador | Investigadora com permissão (U003, horário 09–18) entra no laboratório às 23:40 com a zona fechada e permanece (movimento): acesso fora do horário autorizado que exige verificação. |
| B01 | não | NONE | Cartão mal lido | Recusa seguida de acesso concedido 20 s depois, mesmo utilizador e porta, dentro do horário e com permissão: leitura falhada do cartão. |
| B02 | não | NONE | Investigadora após o fecho do laboratório, dentro do seu turno | U033 tem horário 10–19; entra no laboratório às 18:30 (zona fecha às 18:00) dentro do seu turno e com permissão. |
| B03 | não | NONE | Operador do turno noturno na sala de servidores | U018 (it_operator, turno 20:00–08:00, com permissão para Z05) entra às 03:10: atividade esperada no seu turno. |
| B04 | não | NONE | Ronda de segurança noturna | U012 (security, 24h, todas as zonas) entra no arquivo às 01:30 durante a ronda. |
| B05 | não | NONE | Limpeza antes da abertura | U021 (limpeza externa, turno 06–09, permissão Z02) entra nos escritórios às 06:20. |
| B06 | não | LOW | Deteção isolada no armazém | Uma única deteção de movimento no armazém (INTERNAL) às 21:05, sem repetição nem acessos: falso alarme típico do sensor. |
| B07 | não | NONE | Administrador no NOC à noite | U002 (it_admin, permissão Z06) entra às 23:00 no NOC, que funciona 24/7. |
| B08 | não | NONE | Porta errada durante o dia | U041 tenta uma vez a porta do laboratório às 11:00 (sem permissão), sem movimento e sem repetição: engano de porta. |

## Volume gerado

- Eventos de acesso válidos: 88; linhas no CSV (com inválidos e duplicados): 99
- Eventos de sensor: 73 (inclui leituras sem deteção); documentos no JSON: 79
- Eventos de cenário: 37; dias: 2026-10-12, 2026-10-13, 2026-10-14
