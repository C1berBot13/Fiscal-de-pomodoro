# Fiscal de Pomodoro

Assistente Pomodoro com **visão computacional** que monitora seu foco em tempo real usando a câmera do computador. Detecta olhos fechados, desvio de olhar, uso de celular, postura incorreta e ausência — tudo para manter você produtivo durante as sessões de estudo.

---

## Funcionalidades

| Recurso | Descrição |
|---|---|
| **Timer Pomodoro** | Sessões configuráveis de estudo e descanso com contagem regressiva visual |
| **Monitoramento por câmera** | Detecta olhos fechados, rosto virado, celular na mão, postura curvada e ausência |
| **Alarme irritante** | Som estridente de alta frequência que toca quando o foco é perdido — para imediatamente ao recuperar o foco |
| **Alarme personalizável** | Escolha qualquer áudio do seu computador e recorte um trecho de 5–10 segundos |
| **Aviso de postura por voz** | Fala "Por favor, corrija a sua postura" em vez de soar o alarme |
| **Aviso de descanso por voz** | Fala "Está no horário de descanso" ao finalizar um ciclo de estudo |
| **Modo Widget flutuante** | Mini-timer arrastável que fica por cima de todas as janelas — ideal para uso minimizado |
| **Diferenciação celular vs mão** | Mão aberta (≥3 dedos) não dispara alarme; mão fechada/segurando objeto sim |

---

## Pré-requisitos

- **Python 3.10+** — [Download aqui](https://www.python.org/downloads/)
  - Marque **"Add python.exe to PATH"** durante a instalação
- **Webcam funcional** (integrada ou USB)
- **Windows 10/11** (para síntese de voz nativa)

---

## Como Executar

### Forma mais simples (Windows)

1. Dê dois cliques no arquivo `iniciar.bat`
2. Na primeira execução, ele criará o ambiente virtual e instalará as dependências automaticamente
3. Os modelos de IA serão baixados automaticamente (~30 MB)

### Forma manual

```bash
# Crie o ambiente virtual
python -m venv .venv

# Ative o ambiente
.venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt

# Execute o aplicativo
python main.py
```

---

## Configurações

### Timer
- Ajuste os tempos de **Estudo** e **Descanso** (em minutos) diretamente na interface

### Alarme Personalizado
1. Clique em **"Escolher Arquivo"** e selecione um áudio (MP3, WAV, OGG, etc.)
2. Configure o **Início do corte** (em segundos) e a **Duração** (5–10 segundos)
3. Clique em **"Salvar e Aplicar Alarme"**
4. Use **"Usar Padrão"** para voltar ao alarme irritante gerado automaticamente

### Modo Widget
- Clique em **"🗕 Modo Widget"** para minimizar o app em um mini-timer flutuante
- Arraste-o para qualquer posição na tela
- Use os botões ⏸ (pausar/retomar), ⏭ (pular fase) e ⬜ (expandir)

---

## Tecnologias Utilizadas

- **[MediaPipe](https://ai.google.dev/edge/mediapipe/solutions/guide)** — Face Mesh, Pose, Hands e Object Detection
- **[OpenCV](https://opencv.org/)** — Captura e processamento de vídeo
- **[CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)** — Interface gráfica moderna
- **[Pygame](https://www.pygame.org/)** — Reprodução de áudio
- **[Pillow](https://pillow.readthedocs.io/)** — Processamento de imagens

---

