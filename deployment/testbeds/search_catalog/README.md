# Search Catalog Testbeds (Postman/Newman)

Estes testbeds foram simplificados para um único estado-base do catálogo: limpar tudo e semear apenas os assets definidos em `TB02 - Seed All Assets`.

## Pré-requisitos

- `newman` instalado (`npm i -g newman`)
- API key no ambiente (opcional):

```bash
export API_KEY=password
```

## Execução

Cada script aceita 0..N hosts. Se não passares host, usa `http://192.168.112.126/provider/cp`.

```bash
./deployment/postman/clean_assets.sh
./deployment/postman/seed_assets.sh http://127.0.0.1/provider/cp
```

## Fluxo

1. `clean_assets.sh`
- Executa apenas o folder `Cleanup` da coleção Postman.

2. `seed_assets.sh`
- Executa `Cleanup` e, de seguida, o folder `TB02 - Seed All Assets`.
- Este é o seed base para a futura plataforma de testbed.
- Atualmente semeia 18 assets renováveis do cenário TB02: solar, wind, hydro e biomass.

## Notas

- A coleção usada é `deployment/postman/search_catalog_testbeds.postman_collection.json`.
- A coleção mantém apenas os folders `Cleanup` e `TB02 - Seed All Assets`.
- Os scripts executáveis vivem agora em `deployment/postman`.
- O script `seed_assets.sh` garante um catálogo limpo antes do seed.

## Avaliacao automatizada

Foi adicionado um runner comum para executar as queries por grupo de teste e gravar todo o IO num ficheiro:

- Configuracao dos casos: `deployment/testbeds/search_catalog/use_cases.json`
- Runner Python: `deployment/testbeds/search_catalog/run_use_case.py`
- Wrappers shell: `deployment/testbeds/search_catalog/scripts`
- Resultados por omissao: `deployment/testbeds/search_catalog/results`

### Pre-requisitos adicionais

- Ambiente Python do projeto instalado
- `LLM_MODEL` configurado, ou passado via `--model`
- `EMBEDDING_MODEL` configurado
- Ollama e os endpoints EDC acessiveis

### Listar use cases disponiveis

```bash
python3 deployment/testbeds/search_catalog/run_use_case.py --list
```

### Executar um use case

```bash
./deployment/testbeds/search_catalog/scripts/run_contextual.sh
./deployment/testbeds/search_catalog/scripts/run_use_case.sh contextual --model qwen3:8b
```

### Executar todos

```bash
./deployment/testbeds/search_catalog/scripts/run_all_use_cases.sh
```

### Output gerado

Cada execucao escreve dois ficheiros em `deployment/testbeds/search_catalog/results`:

- `*.log` com input, greeting, output do agente, assets extraidos e checks
- `*.json` com o mesmo conteudo em formato estruturado

Regra de avaliacao (modo estrito):

- Se um teste tiver `expected_present`/`expected_absent`, apenas os assets em `expected_present` podem aparecer.
- Qualquer asset extra e marcado como falha (`unexpected_extra_asset`).
- Para excecoes especificas, podes ativar `allow_additional_assets: true` no teste em `use_cases.json`.

Podes tambem fixar os caminhos manualmente:

```bash
python3 deployment/testbeds/search_catalog/run_use_case.py semantic_ambiguity \
  --output /tmp/semantic_ambiguity.log \
  --json-output /tmp/semantic_ambiguity.json
```

### Scripts disponiveis

- `run_no_results.sh`
- `run_return_all.sh`
- `run_specific_n.sh`
- `run_contextual.sh`
- `run_explicit_exclusion.sh`
- `run_requested_zero_found.sh`
- `run_semantic_ambiguity.sh`
- `run_synonyms.sh`
- `run_partial_satisfaction.sh`
- `run_quantity_context_conflict.sh`
- `run_misleading_asset.sh`
- `run_all_use_cases.sh`

---
## Queries

### Nao devolve nenhum:
- "Preciso de dados sobre emissões de CO₂ do setor da aviação comercial europeia."
    - Aviação e emissões não têm cobertura na testbed.
- "Quero informação sobre tarifas de importação de painéis solares na União Europeia."
    - Domínio económico/comercial, não energético/ambiental.
- "Looking for datasets on electric vehicle charging infrastructure in Portugal."
    - EV charging — fora do escopo de renováveis da testbed.

### Devolve todos
- "Quero explorar todos os datasets de energias renováveis que tens disponíveis."
    - Pedido explícito de exploração total — deve listar os 18 assets.
- "Que dados existem sobre produção, recursos e impacto das fontes renováveis em Portugal?"
    - Query abrangente que cobre produção (solar, eólica, hídrica, biomassa), recursos (vento, irradiância, caudais) e impacto (SOL-05).
- "I need an overview of all available renewable energy data for Portugal."
    - Versão inglesa do pedido global — testa cobertura cross-language do embedding.

### Devolve N especifico
- "Dá-me 3 datasets sobre energia solar."
    - 4 assets solares existem — o modelo deve selecionar os 3 mais relevantes e parar. (SOL-01, SOL-02, SOL-04)
- "Preciso de exactamente 2 fontes de dados sobre vento para um relatório."
    - 5 assets eólicos — deve retornar os 2 mais centrais (medições e previsão). (WIN-01, WIN-04)
- "Show me 4 datasets related to hydrological or water resources."
    - Existem exactamente 4 assets hídricos — deve devolver todos.

### Devolve por contexto
- "Estou a desenvolver um modelo de previsão de geração solar para horizonte de 24h. Que dados me são úteis?"
    - SOL-01 (irradiância real) e WIN-04 (NWP) são inputs típicos. SOL-03 tem benchmarks, não séries — não deve aparecer. (SOL-01, WIN-04, ~SOL-03)
- "Quero perceber o impacto ambiental e territorial das renováveis em Portugal."
    - SOL-05 (impacto biodiversidade) e HYD-03 (análise ambiental mini-hídricas) são os únicos com foco ambiental. (SOL-05, HYD-03, ~SOL-01, ~WIN-01)
- "I need to assess water availability for hydropower planning during drought years."
    - HYD-01 (caudais) e HYD-04 (índice PDSI/seca) são directamente relevantes. HYD-02 (produção) e HYD-03 (potencial) não respondem à questão de disponibilidade hídrica. (HYD-01, HYD-04, ~HYD-02, ~HYD-03)

### Exclusao explicita
- "Preciso de dados de irradiância solar em Portugal para calibrar sensores."
    - SOL-02 exclui irradiância explicitamente. SOL-03 também não tem séries. Só SOL-01 serve. (SOL-01, ~SOL-02, ~SOL-03)
- "Quero dados de produção elétrica de parques eólicos onshore."
    - WIN-03 exclui produção. WIN-05 exclui produção elétrica. WIN-02 tem fichas técnicas mas é o mais próximo — WIN-01 também pode aparecer (offshore). (WIN-02, ~WIN-03, ~WIN-05)
- "Estou à procura de séries temporais de biomassa sólida consumida em centrais."
    - BIO-03 exclui biomassa sólida explicitamente (é biogás). BIO-02 tem exactamente o que é pedido. (BIO-02, ~BIO-03)

### X pedido, 0 encontrados
- "Preciso de dados de geração solar em tempo real com resolução inferior a 1 minuto."
    - Nenhum asset tem dados em tempo real nem resolução sub-minuto.
- "Quero benchmarks de modelos de previsão para energia hídrica."
    - SOL-03 tem benchmarks mas só para solar. Não há equivalente para hídrica.
- "Looking for offshore wind power generation time series."
    - WIN-01 tem medições offshore mas não produção. WIN-02 tem produção mas só onshore. Nenhum cobre offshore + produção em conjunto.

### Ambiguidade Semântica
- "Quero dados para otimizar o despacho de energia renovável na rede."
    - Despacho envolve flexibilidade (hídrica com bombagem), previsão (WIN-04), e produção FV (SOL-02). HYD-02 deve rankear mais alto por incluir dados de bombagem. (HYD-02, WIN-04, SOL-02)
- "Preciso de dados históricos de produção renovável para um modelo de machine learning."
    - Query genérica que puxa produção de todos os temas. O modelo deve rankear séries temporais acima de fichas técnicas ou estudos. (SOL-02, WIN-01, HYD-01, BIO-02)
- "What weather and climate data is available for renewable energy analysis?"
    - Clima/meteorologia é transversal — irradiância, NWP, seca e anemometria são todos relevantes. Deve rankear acima de assets de produção ou inventário. (SOL-01, WIN-04, HYD-04, WIN-01)

### Sinónimos terminologia
- "Quero dados de radiação solar — quanto sol bate em cada zona de Portugal."
    - Radiação solar / 'quanto sol bate' deve mapear para GHI/DNI/irradiância. Testa se o keyword generation faz a ponte lexical. (sol-01, sol-04)
- "I need woodchip and pellet price data for biomass energy."
    - Woodchip = estilha. Testa se o modelo expande para terminologia portuguesa equivalente. (bio-04)
- "Quero previsões numéricas de vento — NWP ou similar — para Portugal."
    - NWP está na descrição de WIN-04. Query mistura inglês técnico e português — testa robustez do embedding em queries híbridas. (WIN-04)

### Satisfação parcial
- "Preciso de um dataset que tenha ao mesmo tempo perfis verticais de vento e curvas de potência de turbinas."
    - WIN-01 tem perfis de vento. WIN-03 tem curvas de potência. Nenhum tem os dois — o modelo deve identificar ambos e notar que é necessário cruzá-los. (WIN-01, WIN-03)
- "Quero dados de caudais fluviais e ao mesmo tempo produção hídrica das albufeiras, tudo junto."
    - HYD-01 tem caudais. HYD-02 tem produção de albufeiras. Estão separados — o modelo não deve fingir que um deles cobre os dois.(HYD-01, HYD-02)
- "I'm looking for a single dataset with both onshore wind measurements and electricity generation."
    - WIN-05 tem medições mas exclui produção. WIN-02 tem fichas técnicas de parques mas não séries de geração. Satisfação parcial + exclusão em simultâneo. (WIN-05, WIN-02)

### Conflito quantidade/contexto
- "Dá-me 5 datasets sobre mini-hídricas ou pequena hídrica."
    - Só existe 1 asset sobre mini-hídricas. O modelo deve retorná-lo e informar que não há mais. (HYD-03)
- "Quero 4 datasets exclusivamente sobre biogás."
    - Só BIO-03 é sobre biogás. O modelo não deve incluir BIO-02 (biomassa sólida) para completar 4.
- "Find me 6 datasets about offshore renewable energy."
    - Só WIN-01 é claramente offshore. O modelo não deve forçar outros assets para chegar a 6.

### Asset enganador
- "Preciso de dados de geração fotovoltaica — produção em MWh de parques solares."
    - SOL-05 tem 'fotovoltaico' no título e tags mas exclui explicitamente produção energética. A similaridade semântica vai puxá-lo — a LLM tem de o rejeitar. (SOL-02, ~SOL-05)
- "Quero dados de vento a 80m e 120m de altura para estimar produção eólica."
    - WIN-05 tem perfis de vento a 80m e 120m, mas o contexto é acústico e exclui produção. Deve ser rejeitado apesar da alta similaridade semântica. (WIN-01, WIN-04, ~WIN-05)
- "I need natural gas price comparisons for energy market analysis."
    - BIO-04 menciona gás natural na comparação de preços, mas o asset é sobre biomassa. Não deve ser retornado para uma query sobre mercado de gás. (~BIO-04)
