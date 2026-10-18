# Entrelinhas

Leitor de PDF para Windows, com interface nativa em português e biblioteca local.

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

## Organizar a biblioteca

- **Organizar**: altere o nome exibido, as tags, a pasta e o favorito do livro selecionado.
- **Pastas +**: crie pastas; escolha uma pasta existente no campo "Dentro de" para criar subpastas.
- Clique com o botão direito em uma pasta para renomear, criar subpasta ou excluir.
  Excluir pastas preserva os livros e marcadores em "Sem pasta".
- Em **Minha ordem**, arraste os livros ou use os botões de seta inferiores.
  Ao ordenar uma seleção filtrada, os demais livros conservam suas posições.
- Busque por nome, nome original do arquivo ou tags. As buscas da biblioteca ignoram acentos.
- Clique com o botão direito no livro para exportar uma cópia ou removê-lo.
  Remover um livro exclui a cópia da biblioteca e os marcadores; preserva o arquivo original.
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
- `biblioteca.sqlite3`: nomes, pastas, tags, ordem, favoritos, marcadores e preferências.

O uso não requer conta, servidor ou conexão com a internet. O aplicativo não envia seus
livros para serviços externos. Em **Preferências → Criar backup**, salve um ZIP em outra
pasta. Para restaurar ou mudar de computador: feche o aplicativo, guarde uma cópia da
pasta de dados atual e extraia o ZIP para uma pasta de dados vazia em `%LOCALAPPDATA%/LeitorPDF`.
O banco e a pasta `pdfs` devem ficar juntos. Não substitua um banco enquanto o aplicativo estiver aberto.

## Desenvolvimento

Python 3.12+ e bibliotecas Qt Widgets/Qt PDF do PySide6. Não usa HTML, navegador ou servidor web.

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
