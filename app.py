# Leitor de QR Code para extração de chaves de acesso (44 dígitos)

import streamlit as st
from PIL import Image
from pyzbar.pyzbar import decode
import pandas as pd
import os
import cv2
import numpy as np
import sys
# Importação para acesso à câmera/webcam
from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
import re

# --- Configuração Inicial e Funções ---

# Forçar as colunas a serem string, essencial para chaves de 44 dígitos
CSV_DTYPE = {'Chave': str}
ARQUIVO_CHAVES = "chaves.csv"

def processar_imagem(img_pil):
    """Aplica técnicas para maximizar detecção de QR Code"""
    img_array = np.array(img_pil)
    # Converte para RGB se tiver canal alfa (RGBA)
    if img_array.shape[2] == 4:
        img_array = cv2.cvtColor(img_array, cv2.COLOR_RGBA2RGB)
    
    tecnicas = []
    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)
    
    # Técnicas básicas
    # Nota: A primeira entrada é sempre a imagem original (RGB ou Cinza)
    tecnicas.append(("Original", img_array))
    tecnicas.append(("Cinza", gray))
    
    # Técnicas OpenCV
    _, otsu = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    tecnicas.append(("Otsu", otsu))
    
    adaptivo = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    tecnicas.append(("Adaptativo", adaptivo))
    
    equalizado = cv2.equalizeHist(gray)
    tecnicas.append(("Equalizado", equalizado))
    
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    clahe_img = clahe.apply(gray)
    tecnicas.append(("CLAHE", clahe_img))
    
    bilateral = cv2.bilateralFilter(gray, 9, 75, 75)
    tecnicas.append(("Bilateral", bilateral))
    
    # Rotações e escalas
    todas_tentativas = []
    # Itera sobre todas as técnicas de pré-processamento
    for nome, img in tecnicas:
        # Itera sobre rotações
        for angulo in [0, 90, 180, 270]:
            if angulo == 0:
                img_rot = img
            else:
                # np.rot90 é mais eficiente para rotações de 90 graus
                img_rot = np.rot90(img, k=angulo//90)
            
            todas_tentativas.append((f"{nome}_{angulo}°", img_rot))
            
            # Aplica escalas em cada rotação
            for escala in [0.7, 1.5]:
                try:
                    h, w = img_rot.shape[:2]
                    novo_w, novo_h = int(w * escala), int(h * escala)
                    # INTER_CUBIC para aumento de escala, INTER_AREA para redução
                    interp = cv2.INTER_CUBIC if escala > 1 else cv2.INTER_AREA
                    img_esc = cv2.resize(img_rot, (novo_w, novo_h), interpolation=interp)
                    todas_tentativas.append((f"{nome}_{angulo}°_{escala}x", img_esc))
                except Exception:
                    # Ignora se a imagem for muito pequena e o resize falhar
                    continue
    
    return todas_tentativas

def ler_qr_code(img_pil):
    """Tenta ler QR Code com múltiplas técnicas"""
    # 1. Tentar original primeiro (o mais rápido)
    resultado = decode(img_pil)
    if resultado:
        return resultado, "Original", 1
    
    # 2. Aplicar todas as técnicas de otimização
    tentativas = processar_imagem(img_pil)
    
    for i, (nome, img) in enumerate(tentativas, 2):
        try:
            # Converte o array numpy processado de volta para PIL Image para o pyzbar
            if len(img.shape) == 2:
                img_pil_proc = Image.fromarray(img, mode='L') # Grayscale
            else:
                img_pil_proc = Image.fromarray(img.astype('uint8')) # RGB
            
            resultado = decode(img_pil_proc)
            if resultado:
                return resultado, nome, i
        except:
            # Ignora falhas de conversão/decodificação
            continue
    
    return None, f"Falhou após {len(tentativas)+1} tentativas", len(tentativas)+1

def extrair_chave(texto):
    """Extrai chave de acesso (44 dígitos) do texto do QR Code"""
    try:
        # Padrões comuns de URL de cupom fiscal
        if 'p=' in texto:
            return texto.split("p=")[1].split("|")[0]
        if 'chNFe=' in texto:
            return texto.split("chNFe=")[1].split("&")[0]
        
        # Buscar 44 dígitos (padrão NF-e/NFC-e)
        match = re.search(r'\d{44}', texto)
        return match.group() if match else None
    except:
        return None

def salvar_dados(chave):
    """Salva chave no CSV se não existir, garantindo formato de texto com apóstrofo."""
    
    # Prepara a chave com um apóstrofo na frente para forçar o formato texto
    chave_formatada = f"'{chave}"
    nova_linha = pd.DataFrame({'Chave': [chave_formatada]}, dtype=str)
    
    if os.path.exists(ARQUIVO_CHAVES):
        # Lê o CSV forçando a coluna 'Chave' a ser string
        df = pd.read_csv(ARQUIVO_CHAVES, dtype=CSV_DTYPE)
        
        # Limpa o apóstrofo para verificar se a chave já existe
        chaves_existentes = df['Chave'].str.replace("'", "", regex=False).values
        chave_limpa = chave.replace("'", "")
        
        if chave_limpa in chaves_existentes:
            return False  # Já existe
        
        df = pd.concat([df, nova_linha], ignore_index=True)
    else:
        df = nova_linha
    
    # Salva o CSV
    df.to_csv(ARQUIVO_CHAVES, index=False)
    return True  # Nova chave salva

# --- Leitura em Tempo Real (Classe VideoTransformer) ---

class QRReader(VideoTransformerBase):
    """Processa frames de vídeo para detectar QR Codes em tempo real"""
    
    def transform(self, frame):
        # Converte o frame para array numpy
        img = frame.to_ndarray(format="bgr24")
        
        # O estado 'qr_lock_success' é usado para parar o loop de leitura após o sucesso
        if not st.session_state.get('qr_lock_success', False): 
            
            # Converte para PIL Image e RGB para o pipeline de otimização
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_pil = Image.fromarray(img_rgb)
            
            # Tenta ler o QR Code com o pipeline otimizado
            resultado, metodo, _ = ler_qr_code(img_pil)

            if resultado:
                texto = resultado[0].data.decode("utf-8")
                chave = extrair_chave(texto)
                
                # Coordenadas do QR Code para feedback visual
                (x, y, w, h) = resultado[0].rect
                
                if chave:
                    if salvar_dados(chave):
                        # CHAVE SALVA (Sucesso)
                        st.session_state['qr_lock_success'] = True
                        st.session_state['last_detected_key'] = chave
                        st.success(f"🔑 Chave de acesso detectada e SALVA com sucesso!")
                        
                        # Feedback visual: Retângulo VERDE
                        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 3)
                        cv2.putText(img, "CHAVE SALVA!", (x, y - 10), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 255, 0), 2)
                        
                        # Recarrega o Streamlit para atualizar a tabela de chaves salvas
                        st.rerun() 
                        
                    else:
                        # CHAVE JÁ EXISTE (Aviso)
                        st.session_state['qr_lock_success'] = True
                        st.warning("⚠️ Chave detectada, mas JÁ EXISTE no registro!")
                        
                        # Feedback visual: Retângulo AMARELO
                        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 255), 3)
                        cv2.putText(img, "JA EXISTE", (x, y - 10), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 255, 255), 2)
                        
                else:
                    # QR CODE LIDO, MAS CHAVE INVÁLIDA
                    cv2.rectangle(img, (x, y), (x + w, y + h), (0, 165, 255), 3) # Laranja
                    cv2.putText(img, "CHAVE INVALIDA", (x, y - 10), cv2.FONT_HERSHEY_DUPLEX, 0.7, (0, 165, 255), 2)
            
            # Se a leitura falhar, desenha um retângulo vermelho para indicar busca
            # else:
            #     # Omissão intencional para evitar flickering excessivo
            #     pass

        return img

# --- Interface Streamlit ---

st.set_page_config(page_title="Leitor QR Code", layout="centered")
st.title("📱 Leitor de QR Code - Cupons Fiscais")
st.write("Sistema eficaz para extrair chaves de acesso (44 dígitos)")

# Inicializa o estado de sucesso da câmera
if 'qr_lock_success' not in st.session_state:
    st.session_state['qr_lock_success'] = False

# 1. Abas para organizar as opções
tab_camera, tab_upload = st.tabs(["📹 Câmera em Tempo Real", "📤 Upload de Imagem"])

# --- TAB: Câmera em Tempo Real ---
with tab_camera:
    st.header("Digitalização com Câmera (Live)")
    st.info("Aponte sua câmera para o QR Code. A leitura para automaticamente após o sucesso.")
    
    # Componente de streaming
    try:
        webrtc_ctx = webrtc_streamer(
            key="qr-code-scanner", 
            video_processor_factory=QRReader,
            # Configuração STUN (necessária para rodar na internet/celular)
            rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
            media_stream_constraints={"video": True, "audio": False}
        )
    except Exception as exc:
        # Import here to avoid failing the module import when package is missing
        try:
            from streamlit_webrtc.session_info import NoSessionError
        except Exception:
            NoSessionError = None

        # If it's the expected NoSessionError, print a clear instruction and exit.
        if NoSessionError is not None and isinstance(exc, NoSessionError):
            msg = (
                "This app must be run with Streamlit.\n"
                "Run it like: `streamlit run app.py`\n"
                "Running with `python app.py` will not create the Streamlit runtime/context required by streamlit-webrtc."
            )
            # When executed from a terminal, print the message for the user
            print(msg)
            # Also show a Streamlit error if possible
            try:
                st.error(msg)
            except Exception:
                pass
            sys.exit(1)
        else:
            # Re-raise unexpected exceptions
            raise
    
    if webrtc_ctx.state.playing:
        if st.button("🔄 Reiniciar Leitura"):
            # Reseta o estado para permitir nova detecção
            st.session_state['qr_lock_success'] = False
            st.rerun() # Força o rerun para reiniciar o processamento

# --- TAB: Upload de Imagem ---
with tab_upload:
    st.header("Digitalização de Foto")
    arquivo_img = st.file_uploader("Selecione uma imagem (PNG, JPG, JPEG)", type=["png", "jpg", "jpeg"])

    if arquivo_img:
        img = Image.open(arquivo_img)
        st.image(img, width=300, caption="Imagem Carregada")
        
        with st.spinner("🔍 Processando imagem com múltiplas técnicas..."):
            resultado, metodo, tentativas = ler_qr_code(img)
        
        if resultado:
            st.success("✅ QR Code detectado!")
            st.info(f"**Método:** {metodo} (tentativa {tentativas})")
            
            texto = resultado[0].data.decode("utf-8")
            chave = extrair_chave(texto)
            
            if chave:
                st.success(f"🔑 **Chave:** `{chave}`")
                
                # Salva garantindo formato texto
                if salvar_dados(chave):
                    st.success("💾 Nova chave salva!")
                else:
                    st.warning("⚠️ Chave já existe no registro!")
            else:
                st.error("❌ Chave não encontrada (44 dígitos) no conteúdo do QR Code")
            
            with st.expander("📋 Texto completo do QR Code"):
                st.code(texto)
        else:
            st.error(f"❌ QR Code não detectado na imagem ({tentativas} tentativas)")


# --- Dados salvos (Rodapé) ---
st.markdown("---")
if os.path.exists(ARQUIVO_CHAVES):
    # Força 'Chave' a ser string ao ler
    df = pd.read_csv(ARQUIVO_CHAVES, dtype=CSV_DTYPE) 
    if not df.empty:
        st.subheader(f"📊 Chaves Salvas ({len(df)})")
        
        # Prepara para exibição: remove o apóstrofo que usamos para formatação CSV
        df_display = df.copy()
        df_display['Chave'] = df_display['Chave'].str.replace("'", "", regex=False) 
        
        st.dataframe(df_display, width='stretch', use_container_width=True)
        
        # Exporta o arquivo com a formatação correta (com o apóstrofo)
        csv_file = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            "📥 Baixar Chaves (CSV)", 
            csv_file, 
            ARQUIVO_CHAVES, 
            "text/csv",
            help="O arquivo CSV exportado força a chave a ser texto (string) para evitar erros de formatação numérica."
        )
    else:
        st.info("Nenhuma chave salva ainda.")
else:
    st.info("Nenhuma chave salva ainda.")

# Info técnica
with st.expander("Detalhes"):
    st.write("Pré-processamento de imagem e leitura em tempo real via streamlit-webrtc.")