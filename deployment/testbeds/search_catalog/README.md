# Search Catalog Testbeds (Postman/Newman)

Estes testbeds preparam dados no provider para testar o `search-catalog agent`.

## Pré-requisitos

- `newman` instalado (`npm i -g newman`)
- API key no ambiente (opcional):

```bash
export API_KEY=password
```

## Execução

Cada script aceita 0..N hosts. Se não passares host, usa `http://127.0.0.1/provider/cp`.

```bash
./deployment/testbeds/search_catalog/tb01_no_assets.sh
./deployment/testbeds/search_catalog/tb02_all_assets.sh http://127.0.0.1/provider/cp
```

## Cenários

1. `tb01_no_assets.sh`
- Regra: existem assets no catálogo, mas a query não deve retornar nenhum.
- Objetivo: testar falsos positivos semânticos com descrições ambíguas.
- Prompt sugerido: `Quero 2 assets sobre produção eólica offshore e fatores de capacidade de turbinas no mar`.

2. `tb02_all_assets.sh`
- Regra: para a query escolhida, todos os assets semeados devem ser retornados.
- Objetivo: validar cobertura total por keyword + keywords relacionadas geradas pelo LLM.
- Prompt sugerido: `Procura datasets para analytics de energia elétrica, incluindo procura, geração e variáveis exógenas`.

3. `tb03_some_assets.sh`
- Regra: para a query escolhida, deve retornar apenas alguns assets e excluir outros.
- Objetivo: testar precisão/recall parcial.
- Prompt sugerido: `Preciso de dados de mobilidade urbana e trânsito`.

4. `tb04_one_asset.sh`
- Regra: existem vários assets relevantes (incluindo mesmo tópico), mas o utilizador quer apenas 1.
- Objetivo: validar que a resposta final do agente limita para 1 item.
- Prompt sugerido: `Quero apenas 1 asset sobre clima/meteorologia`.

5. `tb05_x_assets.sh`
- Regra: igual ao TB04, mas com número específico `x`.
- Objetivo: validar limitação explícita por cardinalidade pedida.
- Prompt sugerido: `Quero 2 assets sobre energia`.

6. `tb06_x_assets_none_match.sh`
- Regra: o utilizador quer `x` assets sobre um tópico, mas não existe nenhum correspondente.
- Objetivo: validar mensagem de vazio e sugestão de refinar query.
- Prompt sugerido: `Quero 3 assets sobre tráfego marítimo portuário`.

## Notas

- Cada execução faz `Cleanup` antes de fazer `Seed`.
- A coleção usada é `deployment/postman/search_catalog_testbeds.postman_collection.json`.
- Os scripts não validam automaticamente o número de resultados; a validação é observada na resposta do agente.
