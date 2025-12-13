# Amigo Secreto com Streamlit

Este repositório contém um aplicativo web simples de Amigo Secreto
desenvolvido em [Streamlit](https://streamlit.io). O app permite:

* Criar um grupo de amigo secreto com o nome do grupo e a lista de
  participantes.
* Compartilhar um link exclusivo do grupo para que cada participante
  confirme sua participação (fornecendo uma senha). Não reutilize
  senhas reais, pois elas são armazenadas em hash no arquivo `groups.json`.
* Realizar o sorteio quando todos confirmarem a participação.
* Permitir que cada participante descubra quem é o seu amigo secreto
  usando seu nome e senha.

## Como executar localmente

1. Clone este repositório:

   ```sh
   git clone https://github.com/seu-usuario/amigo_secreto_app.git
   cd amigo_secreto_app
   ```

2. Instale as dependências (recomenda‑se usar um ambiente virtual):

   ```sh
   python -m venv .venv
   source .venv/bin/activate  # no Windows: .\.venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Execute o aplicativo:

   ```sh
   streamlit run app.py
   ```

4. Abra o navegador na URL mostrada no terminal (por padrão,
   `http://localhost:8501`).

## Implantação no Streamlit Community Cloud

1. Faça login em [streamlit.io](https://streamlit.io) usando sua conta GitHub.
2. Crie um novo app a partir do seu repositório. Escolha a branch
   principal (por exemplo, `main`) e defina `app.py` como o arquivo principal.
3. Clique em **Deploy**. O Streamlit irá instalar as dependências
   definidas em `requirements.txt` e disponibilizar o app.

Lembre‑se de que, no Streamlit Community Cloud, os dados persistem
enquanto a instância do aplicativo estiver ativa. Para utilização
permanente, considere armazenar os dados em um banco de dados externo
(Firebase, Supabase, Postgres etc.).
