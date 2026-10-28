# Entrelinhas

Leitor de PDF para Windows, com interface nativa em português, biblioteca offline e sincronização online opcional.

## Abrir

Abra `dist/Entrelinhas/Entrelinhas.exe` ou o atalho `Abrir Entrelinhas.lnk`.
Não é necessário instalar Python. Para levar o aplicativo para outro computador,
copie **toda a pasta `dist/Entrelinhas`**, incluindo `_internal`.

## Abrir pelo botão direito no Windows

No Explorador de Arquivos, clique com o botão direito em um PDF e escolha
**Abrir com → Entrelinhas**. Também há a ação **Abrir com Entrelinhas** no menu
clássico (no Windows 11, em **Mostrar mais opções**).

Essa ação **adiciona uma cópia do PDF à biblioteca e abre o livro**. Se o mesmo
arquivo já estiver na biblioteca, ele é aberto sem duplicação, preservando nome,
tags, pastas, marcadores e posição de leitura. Funciona com o aplicativo fechado
ou já aberto. PDFs enviados pelo Windows entram em **Sem pasta**; livros existentes
continuam em suas pastas. O arquivo original não é movido.

Para ativar a integração em outro computador, ou atualizar o caminho após mover
a pasta do programa, use **Preferências → Adicionar ao “Abrir com” do Windows**.
Também é possível executar `Entrelinhas.exe --register-shell`.
A integração é registrada somente para o usuário atual e não troca o leitor de
PDF padrão. Não exige acesso de administrador.

O aplicativo também aceita arquivos na linha de comando:

```powershell
.\dist\Entrelinhas\Entrelinhas.exe "C:\Livros\Meu livro.pdf"
```

## Guardar e reencontrar uma página

1. Clique em **Importar PDFs** e escolha um ou mais arquivos.
2. Dê dois cliques em um livro para ler.
3. Na página desejada, clique em **Marcar página** ou pressione **Ctrl+D**.
4. Dê um nome ao marcador e, se quiser, acrescente uma nota e uma cor.
5. Clique no marcador no painel à direita para voltar àquela página.

**Páginas marcadas**, na barra lateral, reúne os marcadores de todos os livros.
Eles permanecem salvos após fechar o aplicativo. A última página lida também
é salva automaticamente. Os números correspondem às páginas do arquivo PDF,
contando a capa como página 1; podem diferir da numeração impressa no livro.

## Anotar durante a leitura

1. Na página desejada, clique em **Anotar** ou pressione **Ctrl+N**.
2. Escreva o texto e clique em **Salvar anotação**. O número da página é registrado automaticamente.
3. Consulte a aba **Anotações** no painel à direita. É possível criar várias anotações na mesma página.
4. Clique em uma anotação para voltar à página de origem; dê dois cliques ou use **Editar** para alterar o texto.
   A página de origem permanece a mesma após a edição. Use **Excluir** para remover uma anotação.

Em tela cheia ou foco, os controles no topo também oferecem **Anotar** e **Anotações**.
As anotações ficam salvas na biblioteca local, continuam disponíveis ao reabrir o livro e são
incluídas no backup. A numeração conta a primeira página do arquivo como página 1.
As anotações não são incorporadas ao arquivo PDF exportado.

## Organizar a biblioteca

- **Organizar**: altere o nome exibido, as tags, a pasta e o favorito do livro selecionado.
- **Pastas +**: crie pastas; escolha uma pasta existente no campo "Dentro de" para criar subpastas.
- Clique com o botão direito em uma pasta para renomear, criar subpasta ou excluir.
  Excluir pastas preserva os livros e marcadores em "Sem pasta".
- Em **Minha ordem**, arraste os livros ou use os botões de seta inferiores.
  Ao ordenar uma seleção filtrada, os demais livros conservam suas posições.
- Busque por nome, nome original do arquivo ou tags. As buscas da biblioteca ignoram acentos.
- Clique com o botão direito no livro para exportar uma cópia ou removê-lo.
  Remover um livro exclui a cópia da biblioteca, os marcadores e as anotações; preserva o arquivo original.
- Importações idênticas são reconhecidas sem duplicar o livro. Se a cópia local tiver sido
  removida, importar o mesmo original novamente a recupera, preservando os marcadores.

## Leitura e preferências

Há zoom, rolagem contínua ou página individual, sumário embutido do PDF, busca de texto,
três modos de leitura, favoritos e temas claro/escuro. O tema escuro modifica a interface; as cores do
documento permanecem originais. A busca de texto requer texto no PDF; não inclui OCR de
páginas digitalizadas. PDFs protegidos solicitam a senha a cada abertura; senhas não são salvas.

Escolha o modo na barra do leitor:

- **Normal**: biblioteca, ferramentas e painel de marcadores visíveis.
- **Tela cheia — F11**: o PDF ocupa todo o monitor onde está a janela.
- **Foco — Ctrl+F**: tela cheia no monitor da leitura e telas pretas nos demais monitores.

Na tela cheia e no foco, mova o mouse até o topo para revelar os controles.
**Marcar** ou **Ctrl+D** salva a página atual. **Marcadores** abre um painel sobre
o PDF, com acesso às páginas salvas, edição e exclusão. O painel permanece aberto
enquanto você lê, até fechá-lo pelo botão × ou por **Marcadores**.
**Esc** volta ao modo normal, preservando a página e restaurando o tamanho da janela e o zoom.
Pressionar novamente o atalho do modo ativo também volta ao normal.
As telas pretas são retiradas ao alternar para outro aplicativo, minimizar ou fechar
o Entrelinhas, e reaparecem ao voltar ao leitor em modo foco.

| Atalho | Ação |
| --- | --- |
| Ctrl+O | Importar PDFs |
| Ctrl+D | Criar ou editar marcador da página atual |
| Ctrl+N | Criar anotação na página atual |
| Ctrl+F | Alternar modo foco |
| Ctrl+Shift+F | Buscar no livro ou na coleção atual |
| F3 / Shift+F3 | Próximo resultado / resultado anterior da busca |
| Ctrl+G | Digitar número da página; Enter confirma |
| Ctrl+← / Ctrl+→ | Página anterior / próxima |
| F11 | Alternar tela cheia |
| Alt+← | Voltar à biblioteca |
| Esc | Voltar ao modo normal ou limpar busca no PDF |

## Dados e backup

A biblioteca fica em `%LOCALAPPDATA%/LeitorPDF`:

- `pdfs/`: cópias dos PDFs importados;
- `capas/`: miniaturas da primeira página;
- `biblioteca.sqlite3`: nomes, pastas, tags, ordem, favoritos, marcadores, anotações, preferências e fila de sincronização.

O uso local continua sem conta, servidor ou conexão com a internet. Nada é enviado enquanto
a sincronização estiver desativada. Em **Preferências → Criar backup**, salve um ZIP em outra
pasta. Para restaurar ou mudar de computador: feche o aplicativo, guarde uma cópia da
pasta de dados atual e extraia o ZIP para uma pasta de dados vazia em `%LOCALAPPDATA%/LeitorPDF`.
O banco e a pasta `pdfs` devem ficar juntos. Não substitua um banco enquanto o aplicativo estiver aberto.

## Sincronização online em tempo real

O Entrelinhas pode usar um servidor privado para manter vários computadores com a mesma
biblioteca. A sincronização inclui os próprios PDFs, página lida, marcadores, anotações,
nomes, tags, pastas e subpastas, favoritos, ordem e preferências. Alterações feitas sem
internet ficam na fila local e são enviadas ao reconectar. O servidor avisa os outros
computadores imediatamente por um canal de eventos; há também uma verificação periódica.

Para executar o servidor com Docker:

```powershell
$env:ENTRELINHAS_SYNC_TOKEN = "troque-por-uma-chave-longa-e-secreta"
docker compose up -d --build
```

O servidor escuta na porta `8765` e guarda os dados no volume `entrelinhas-data`. Em um
servidor acessível pela internet, publique essa porta atrás de HTTPS e faça backup do volume.
Não exponha o serviço publicamente por HTTP: a chave permite acesso completo à biblioteca.

### Servidor privado pelo Tailscale

O servidor também pode ficar em um dos computadores da biblioteca sem depender da mesma
rede local. Instale o Tailscale em todos os computadores e conecte-os à mesma Tailnet. No
computador servidor, descubra o IP privado com `tailscale ip -4` e faça o servidor escutar
nesse endereço:

```powershell
.\.venv\Scripts\python.exe server.py --host 100.x.y.z --port 8765 --data-dir "$HOME\.entrelinhas-sync"
```

Nos clientes, use `http://nome-do-computador.nome-da-tailnet.ts.net:8765` como URL. Embora a
URL seja HTTP, o tráfego permanece dentro do túnel autenticado e criptografado do Tailscale;
a porta não precisa ser encaminhada no roteador e não fica aberta à internet pública. A chave
da biblioteca continua obrigatória. O computador servidor precisa estar ligado, conectado à
internet e com o Tailscale ativo.

Também é possível executar sem Docker:

```powershell
$env:ENTRELINHAS_SYNC_TOKEN = "troque-por-uma-chave-longa-e-secreta"
.\.venv\Scripts\python.exe server.py --host 0.0.0.0 --port 8765 --data-dir sync-data
```

No aplicativo, abra **Preferências**, marque **Sincronizar esta biblioteca entre
computadores**, informe a URL HTTPS e a mesma chave. Repita nos outros computadores.
O indicador no rodapé mostra **Nuvem sincronizada**, **Sincronizando** ou o motivo pelo
qual a conexão falhou. O PDF recebido é conferido por SHA-256 antes de substituir o arquivo local.

Se dois computadores alterarem o mesmo registro antes de se encontrarem, prevalece a última
operação recebida pelo servidor. Operações repetidas são idempotentes e exclusões também são
replicadas. O histórico do servidor e os PDFs não substituem um backup independente.

## Desenvolvimento

Python 3.12+ e bibliotecas Qt Widgets/Qt PDF do PySide6. A interface continua sendo um aplicativo
nativo; `server.py` é o serviço separado e opcional usado somente para a sincronização.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Uma biblioteca separada pode ser usada com `--data-dir "C:\MinhaBiblioteca"`.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe main.py --smoke-test artifacts\source\report.json
Remove-Item Env:QT_QPA_PLATFORM
.\build.ps1
```

O teste de integração cria PDFs e uma biblioteca temporários, usa os widgets reais,
testa criação e navegação por marcador, fecha e reabre a janela e verifica persistência.
Também verifica pesquisa no PDF, organização, temas e backup. Ele gera capturas dos
widgets e um relatório JSON, sem alterar a biblioteca pessoal. O mesmo teste pode ser
executado no binário com `Entrelinhas.exe --smoke-test caminho-do-relatorio.json`.
Para verificar os monitores reais com uma biblioteca temporária, execute
`.\.venv\Scripts\python.exe tools\verify_reading_modes.py` sem `QT_QPA_PLATFORM=offscreen`.
O teste abre uma janela temporária, alterna os modos em cada monitor e fecha ao terminar.

Documentação técnica utilizada: [Qt PDF](https://doc.qt.io/qtforpython-6/PySide6/QtPdf/index.html),
[QPdfView](https://doc.qt.io/qtforpython-6/PySide6/QtPdfWidgets/QPdfView.html),
[QPdfSearchModel](https://doc.qt.io/qtforpython-6/PySide6/QtPdf/QPdfSearchModel.html).
Modos de leitura: [QWidget.showFullScreen](https://doc.qt.io/qtforpython-6/PySide6/QtWidgets/QWidget.html#PySide6.QtWidgets.QWidget.showFullScreen)
e [QGuiApplication](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QGuiApplication.html).
Integração com o Explorador: [registro de aplicativos no Windows](https://learn.microsoft.com/en-us/windows/win32/shell/app-registration).
As licenças das dependências acompanham a distribuição em `licenses/`.
