# meu-projeto-1

Este projeto usa variáveis de ambiente em vez de chaves embutidas no código.

## Instalação

1. Clone o repositório:
   ```bash
   git clone https://github.com/maxwel7639-pixel/meu-projeto-1.git
   cd meu-projeto-1
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure as variáveis de ambiente:
   - Copie `.env.example` para `.env`
   - Preencha:
     - `GOOGLE_API_KEY`
     - `SUPABASE_URL`
     - `SUPABASE_KEY`
     - `INSTAGRAM_ACCESS_TOKEN`
     - `INSTAGRAM_PAGE_ID`
   - Não adicione `.env` ao controle de versão (já está ignorado em `.gitignore`).

## Uso

### Modo de teste
```bash
python agente.py --test
```

### Ciclo único
```bash
python agente.py
```

### Resumo do dia
```bash
python agente.py --status
```

### Modo de chat interativo
```bash
python agente.py --chat
```

No modo `--chat`, você pode perguntar:
- `status`
- `leads`
- `o que fez`
- `sair`

### Interface web
```bash
python agente.py --web
```

Abra o navegador em `http://127.0.0.1:5000` e use o painel para ver o status do dia e fazer perguntas.

### Deploy para GitHub / hospedagem

- Se quiser apenas subir o HTML no GitHub ou no Lovable, basta hospedar o conteúdo da pasta `web/`.
- Para ter o painel totalmente integrado, o backend Python precisa rodar em um host separado que execute `app.py`.
- O backend já tem CORS habilitado, então o frontend pode chamar a API de outro domínio.
- No painel web, use o campo `URL do backend` para apontar para a URL do servidor Python.

#### Exemplo de deploy integrado

1. Envie o repositório para o GitHub.
2. Se quiser um host Python, use Render, Railway, Heroku ou outro serviço que suporte Flask.
3. O projeto já inclui `app.py`, `Procfile` e `runtime.txt` para facilitar a implantação.
4. No navegador, acesse o frontend estático e informe a URL do backend.

### Loop contínuo
```bash
python agente.py --loop --interval 300
```

### Sincronizar backup
```bash
python agente.py --sync-backup
```

## Dependências

- requests: Para fazer requisições HTTP
- python-dotenv: Para carregar variáveis de ambiente
- supabase: Para integração com Supabase (opcional, usado para backup)

## Configuração do Supabase

Execute o script `setup_supabase.sql` no seu banco de dados Supabase para criar a tabela `leads`.