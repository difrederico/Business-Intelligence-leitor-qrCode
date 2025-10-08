# Leitor de QR Code para extração de chaves de acesso (44 dígitos)

import streamlit as st
from PIL import Image
import types
from dataclasses import dataclass
import pandas as pd
import os
try:
    import cv2
    cv2_available = True
except Exception:
    cv2 = None
    cv2_available = False
import numpy as np
import sys
# Importação para acesso à câmera/webcam
# Import opcional do streamlit-webrtc. Em alguns ambientes (Streamlit Cloud)
# a instalação ou suporte a WebRTC pode não estar disponível. Fazemos um
# import protegido e fornecemos um fallback informativo para a interface.
try:
    from streamlit_webrtc import webrtc_streamer, VideoTransformerBase
    webrtc_available = True
except Exception:
    webrtc_available = False
    webrtc_streamer = None
    # Fallback mínimo para permitir definição da classe utilizada mais abaixo
    class VideoTransformerBase:
        pass
import re

# --- Configuração Inicial e Funções ---

# Forçar as colunas a serem string, essencial para chaves de 44 dígitos
CSV_DTYPE = {'Chave': str}
ARQUIVO_CHAVES = "chaves.csv"

def processar_imagem(img_pil):
    """Aplica técnicas para maximizar detecção de QR Code"""
    # Se o OpenCV não estiver disponível, retornamos uma tentativa simples
    if not cv2_available:
        try:
            arr = np.array(img_pil.convert('RGB'))
            return [("Original", arr)]
        except Exception:
            return []

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


# --- Decoder baseado em OpenCV (substitui pyzbar) ---
@dataclass
class _DetectedQR:
    data: bytes
    rect: tuple

def decode_with_opencv(img_pil):
    """Detecta e decodifica QR Codes usando OpenCV.

    Retorna uma lista de objetos com atributos `data` (bytes) e `rect` (x,y,w,h)
    compatíveis com a API usada pelo restante do código.
    """
    if not cv2_available:
        return []

    img = np.array(img_pil.convert('RGB'))
    detector = cv2.QRCodeDetector()

    # Tenta múltiplas APIs dependendo da versão do OpenCV
    try:
        # detectAndDecodeMulti retorna (ok, decoded_info, points, straight_qrcode)
        ok, decoded_info, points, _ = detector.detectAndDecodeMulti(img)
    except Exception:
        # Fallback para detectAndDecode (um único QR)
        data, points = detector.detectAndDecode(img), None
        if not data:
            return []
        # Points não disponível; estimamos um rect cobrindo toda imagem
        h, w = img.shape[:2]
        return [_DetectedQR(data=data.encode('utf-8'), rect=(0, 0, w, h))]

    results = []
    if ok and decoded_info:
        for i, txt in enumerate(decoded_info):
            if not txt:
                continue
            pt = None
            try:
                pt = points[i]
            except Exception:
                pt = None

            if pt is not None:
                # pt é um array 4x2 (float) com os cantos; calcula bounding box
                xs = pt[:, 0]
                ys = pt[:, 1]
                x, y = int(xs.min()), int(ys.min())
                w_box, h_box = int(xs.max() - xs.min()), int(ys.max() - ys.min())
            else:
                h, w = img.shape[:2]
                x, y, w_box, h_box = 0, 0, w, h

            results.append(_DetectedQR(data=txt.encode('utf-8'), rect=(x, y, w_box, h_box)))

    return results

def ler_qr_code(img_pil):
    """Tenta ler QR Code com múltiplas técnicas"""
    # 1. Tentar original primeiro (o mais rápido) usando OpenCV
    resultado = decode_with_opencv(img_pil)
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
            
            resultado = decode_with_opencv(img_pil_proc)
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
                # 'resultado' agora é uma lista de _DetectedQR
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
    # Permite selecionar câmera frontal ou traseira (quando suportado pelo navegador/ambiente)
    facing_choice = st.selectbox("Escolha a câmera", ["Traseira (recomendada para QR)", "Frontal"], index=0)
    facing_mode = "environment" if facing_choice.startswith("Traseira") else "user"

    # Componente de streaming
    if webrtc_available:
        try:
            # Passamos a preferência de facingMode para o browser quando possível.
            # Note: nem todos os ambientes/browsers respeitam essa preferência.
            media_constraints = {"video": {"facingMode": {"ideal": facing_mode}}, "audio": False}

            # Use uma chave que inclua a escolha de câmera para forçar re-criação do componente
            key_name = f"qr-code-scanner-{facing_mode}"
            webrtc_ctx = webrtc_streamer(
                key=key_name,
                video_processor_factory=QRReader,
                # Configuração STUN (necessária para rodar na internet/celular)
                rtc_configuration={"iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]},
                media_stream_constraints=media_constraints
            )
        except Exception as exc:
            # Falha ao iniciar o componente WebRTC no ambiente atual.
            msg = (
                "Não foi possível inicializar o componente de câmera (streamlit-webrtc).\n"
                "Verifique se a aplicação está sendo executada em um ambiente com suporte a WebRTC.\n"
                "Como alternativa, use a aba 'Upload de Imagem'."
            )
            print(msg)
            try:
                st.error(msg)
            except Exception:
                pass
            webrtc_ctx = None
    else:
        st.warning("Componente de câmera não disponível: a biblioteca 'streamlit-webrtc' não está instalada ou não é suportada no ambiente. Use a aba 'Upload de Imagem' para carregar fotos.")
        webrtc_ctx = None

    if webrtc_ctx and hasattr(webrtc_ctx, 'state') and getattr(webrtc_ctx.state, 'playing', False):
        if st.button("🔄 Reiniciar Leitura"):
            # Reseta o estado para permitir nova detecção
            st.session_state['qr_lock_success'] = False
            st.rerun() # Força o rerun para reiniciar o processamento

    # Fallback: usar st.camera_input quando streamlit-webrtc não estiver disponível
    if not webrtc_available or webrtc_ctx is None:
        try:
            st.info("Alternativa: capture uma foto com sua câmera (funciona no Streamlit Cloud).\nDica: no diálogo de permissão do navegador escolha a câmera traseira se disponível.")
            cam_img = st.camera_input("Tire uma foto do QR Code")
            if cam_img:
                img = Image.open(cam_img)
                st.image(img, width=300, caption="Foto Capturada")
                with st.spinner("🔍 Processando imagem capturada..."):
                    resultado, metodo, tentativas = ler_qr_code(img)

                if resultado:
                    st.success("✅ QR Code detectado!")
                    st.info(f"**Método:** {metodo} (tentativa {tentativas})")
                    texto = resultado[0].data.decode("utf-8")
                    chave = extrair_chave(texto)
                    if chave:
                        st.success(f"🔑 **Chave:** `{chave}`")
                        if salvar_dados(chave):
                            st.success("💾 Nova chave salva!")
                            # atualiza o estado para refletir sucesso
                            st.session_state['qr_lock_success'] = True
                            st.session_state['last_detected_key'] = chave
                            st.experimental_rerun()
                        else:
                            st.warning("⚠️ Chave já existe no registro!")
                    else:
                        st.error("❌ Chave não encontrada (44 dígitos) no conteúdo do QR Code")
                    with st.expander("📋 Texto completo do QR Code"):
                        st.code(texto)
                else:
                    st.error(f"❌ QR Code não detectado na imagem ({tentativas} tentativas)")
        except Exception:
            # Não queremos quebrar a aplicação caso st.camera_input falhe em algum ambiente
            pass

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