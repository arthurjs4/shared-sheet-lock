# shared-sheet-lock (PT-BR)

Permite que duas pessoas, agentes ou computadores usem **a mesma planilha `.xlsx`** sem se atropelar.

- **Trava com expiração** (padrão 4 h) que identifica o dono; trava vencida pode ser reassumida.
- **Reserva de recurso**: um item (ex.: uma região ou lote) por vez.
- **Barreira de duplicata** ao gravar: telefone, site e nome sem acento.
- **Backup do dia** antes da primeira gravação.
- **Nunca apaga linha**; gravação atômica.

Uso, CLI e detalhes técnicos: veja o [README em inglês](README.md). Testes: `pytest` (inclui dois processos escrevendo ao mesmo tempo sem perder dados).

Licença MIT.
