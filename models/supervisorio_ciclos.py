

from ....addons.steril_supervisorio.models.supervisorio_ciclos import dict2tuple
from odoo import models, fields, api, _
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timedelta
import os
import base64
from reportlab.lib.pagesizes import letter, A4
from reportlab.pdfgen import canvas

import io

import logging
_logger = logging.getLogger(__name__)

def timedelta_to_hms(delta):
    """
    Converte um objeto timedelta em horas, minutos e segundos.

    Args:
        delta (timedelta): O intervalo de tempo a ser convertido.

    Returns:
        tuple: Uma tupla (horas, minutos, segundos).
    """
    total_seconds = delta.total_seconds()
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return int(hours), int(minutes), int(seconds)




class SupervisorioCiclosBraile(models.Model):
    

    _description = 'Ciclos do supervisorio da Braile'
    _order = 'data_inicio desc'
    _inherit = ['steril_supervisorio.ciclos']

    grafico_ciclo_distribuition = fields.Binary()
    range_min = fields.Float(string='Range min', default = 30.0)
    range_max = fields.Float(string='Range min', default = 34.0)
    

    def replace_date_in_times(self,time_objects, specific_date):
        """
        Substitui o ano, mês e dia em uma lista de objetos datetime por uma data específica.

        Args:
            time_objects (list): Lista de objetos datetime contendo apenas horas, minutos e segundos.
            specific_date (str): String representando a data no formato "%Y-%m-%d".

        Returns:
            list: Lista de objetos datetime com a data especificada e as horas originais.
        """
        # Converte a data específica para um objeto datetime
        date_object = datetime.strptime(specific_date, "%Y-%m-%d")

        # Substitui ano, mês e dia em cada objeto de tempo
        updated_datetimes = [
            t.replace(year=date_object.year, month=date_object.month, day=date_object.day)
            for t in time_objects
        ]
        total_time = timedelta()
        days_elapsed = 0
        for i in range(1, len(updated_datetimes)):
            updated_datetimes[i] += timedelta(days=days_elapsed) 
            if updated_datetimes[i]  < updated_datetimes[i - 1]:
                days_elapsed +=1
                print(days_elapsed)
                updated_datetimes[i] += timedelta(days=1)

        return updated_datetimes

    def report_duration_cycle(self):
        data = self.get_data_sanitized()
        times = [str(entry[0]) for entry in data]
        total_time = self.calculate_total_time(times)
        return total_time
    
    def report_mount_grid_data(self):
        data = self._get_cycle_data()
        
        return data
    def report_time_in_the_range(self):
        data = self.get_data_sanitized()
        if not data:
            return None
        range_max = self.range_max
        range_min = self.range_min
        _logger.debug(data)

        colocacao_sensores = self.calcular_colocacoes_por_canal(data, range_min)
        _logger.debug(colocacao_sensores)

        # Extraindo os tempos (eixo X) e as temperaturas de cada canal (eixo Y)
        times = [str(entry[0]) for entry in data]
        if len(times) < 1:
            return
        temperatures = [entry[1:] for entry in data]  # Remove o tempo, mantendo apenas as temperaturas

        # Calcular o tempo total
        total_time = self.calculate_total_time(times)

        # Calcular o tempo total em que todas as temperaturas ficaram entre 30 e 34 graus
        hora,min,sec,total_seconds = self.calculate_time_in_range(times, temperatures, range_min, range_max)
        return f"{hora}h, {min}m, {sec}s"
    
    def report_stabilization_time(self):
        data_cycle = self.get_data_sanitized()
        if not data_cycle:
            return None
        times = [str(entry[0]) for entry in data_cycle]
        temperatures = [entry[1:] for entry in data_cycle]  # Remove o tempo, mantendo apenas as temperaturas
        total_time = self.calculate_total_time(times)
        time_in_the_range = self.calculate_time_in_range(times, temperatures, self.range_min, self.range_max)
        stabilization  =  total_time[3] - time_in_the_range[3]
        hour,minute, second = timedelta_to_hms(stabilization)
        return f"{hour}h, {minute}m, {second}s"

    def time_to_datetime(self,times):
        time_objects = [datetime.strptime(t, "%H:%M:%S") for t in times]
        time_objects = self.replace_date_in_times(time_objects, self.data_inicio.strftime("%Y-%m-%d"))
        return time_objects
        

    def calculate_total_time(self,times):
        time_objects = self.time_to_datetime(times)
        
       
       
        total_time = time_objects[-1] - time_objects[0]
           
        # Retornar o tempo total em horas, minutos e segundos
        total_seconds = int(total_time.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return hours, minutes, seconds, total_time
    
    # Função para calcular tempo total em que todas as temperaturas ficaram dentro de um intervalo
    def calculate_time_in_range(self,times, temperatures, lower, upper):
        time_objects = [datetime.strptime(t, "%H:%M:%S") for t in times]
        time_objects = self.replace_date_in_times(time_objects, self.data_inicio.strftime("%Y-%m-%d"))
        total_time_in_range = timedelta()

        for i in range(1, len(time_objects)):
            if all(lower <= temp <= upper for temp in temperatures[i]):
                total_time_in_range += time_objects[i] - time_objects[i - 1]

        # Retornar o tempo total em horas, minutos e segundos
        total_seconds = int(total_time_in_range.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return hours, minutes, seconds, total_time_in_range

    # Função para determinar a primeira hora em que todas as temperaturas excedem um valor
    def find_time_all_above(self,times, temperatures, threshold):
        for i, temps in enumerate(temperatures):
            if all(temp > threshold for temp in temps):
                return times[i]
        return None
    
    def calcular_colocacoes_por_canal(self,dados, temp_alvo):
        # Lista para armazenar o tempo de chegada da temperatura alvo para cada canal
        primeira_chegada = []

        # Dicionário para verificar se o canal já atingiu a temperatura alvo
        canais_atingidos = {i: False for i in range(8)}
        if not dados:
            return 0
        # Percorrer os dados para cada linha (hora e 8 canais de temperatura)
        for hora, *temperaturas in dados:
            # Verificar quando cada canal atingir a temperatura alvo pela primeira vez
            for i, temperatura in enumerate(temperaturas):
                if float(temperatura) >= temp_alvo and not canais_atingidos[i]:
                    # Armazenar a primeira vez que o canal atingiu a temperatura
                    primeira_chegada.append((i + 1, hora, temperatura))
                    canais_atingidos[i] = True  # Marcar o canal como atingido
                    # Verificar se todos os canais já atingiram
                    if len(primeira_chegada) == 8:
                        return sorted(primeira_chegada, key=lambda x: x[1])  # Ordenar pelo tempo

        # Caso não tenha atingido todos os canais, retorna as que atingiram
        return sorted(primeira_chegada, key=lambda x: x[1])  # Ordena pelas horas de chegada
    
    def add_data_file_to_record(self):
        
        value = {}
        #lendo arquivo com os dados do ciclo
        _logger.debug(f"Entrando na add_data_file_to_record da braile")
        data_cycle = self.get_data_sanitized()
        print(data_cycle)
        self.report_stabilization_time()
        
        # pegando as configuraç~eos de fase
        #path_file_ciclo_txt
       
                   
        #se ciclo finalizado
        start_cycle_time = data_cycle[0][0]
        end_cycle_time = data_cycle[-1][0]
        times = [str(entry[0]) for entry in data_cycle]
        hora,minuto,segundo,timedelta_elapsed_time = self.calculate_total_time(times)
        times_with_date = self.replace_date_in_times([datetime.strptime(t, "%H:%M:%S") for t in times],self.data_inicio.strftime("%Y-%m-%d"))
        
        time_zero = timedelta()
        print(times_with_date[-1])
        if len(times_with_date) > 1:  
             self.write({
                 'state':'finalizado',
                 'data_fim': times_with_date[-1]+timedelta(hours=3) # mais 3 horas do fuso horario
                 
             })
        # else:
        #     if self.identifica_ciclo_incompleto(self.data_inicio):
        #         time_cycle_duration = do.compute_elapsed_time(start_time=start_cycle_time,end_time = end_cycle_time)
        #         #Procurando se finalizou na ultima fase mesmo sem ciclo abortado
        #         fase_end = self.env['steril_supervisorio.ciclos.fases.eto'].search(['&',('name','=', phases_name[-2]),('ciclo','=',self.id)])
        #         if len(fase_end) > 0:
        #             state = 'finalizado'
        #         else:
        #             state = 'incompleto'
                    
        #         self.write({
        #             'state':state,
        #             'data_fim': self.data_inicio + time_cycle_duration
        #         })
        #     else:
        #         self.write({
        #             'state':'em_andamento'
        #         })

        return 0
    
    def get_data_sanitized(self):
        data = []
        do = self._get_dataobject_cycle()
        if not do:
            _logger.warning(f"Não foi possível montar o gráfico ciclo {self.name}, data_object retornou False")
            return False
        data_raw = self._get_cycle_data()
        for d in data_raw:
            data.append(dict2tuple(d))
        if not data:
            _logger.warning(f"Não foi possível encontrar no ciclo {self.name} o data_object retornou False")
            return None

        if len(data) < 1:
            _logger.warning(f"Nenhum dado foi encontrado no ciclo {self.name}")
            return None
        
        return data

    def adicionar_anexo_pdf(self):
        """
        Adiciona um anexo ao modelo atual a partir de um arquivo local. 

        
        :param caminho_arquivo: Caminho completo do arquivo local a ser anexado com o nome do arquivo .
        :return: O objeto de anexo criado ou retorna false caso não exista o arquivo em pdf
        """

        caminho_arquivo = self.path_file_ciclo_txt
        print(caminho_arquivo)
        nome_arquivo = os.path.basename(caminho_arquivo)
       
        # Lê o conteúdo do arquivo TXT
        with open(caminho_arquivo, 'r', encoding='utf-8') as txt_file:
            txt_content = txt_file.readlines()

        # Generate a temporary file path for the PDF
        pdf_filename = f"{self.name or 'arquivo'}.pdf"
        temp_pdf_path = f"/tmp/{pdf_filename}"
        page_width, page_height = A4
        margin = 50
        line_height = 12  # Altura de cada linha de texto
        max_lines_per_page = int((page_height - 2 * margin) / line_height)

        # Create PDF using reportlab
        c = canvas.Canvas(temp_pdf_path, pagesize=A4)
        
        # Variáveis de controle de página
        y_position = page_height - margin
        current_line = 0

        # Escreve o conteúdo no PDF
        for line in txt_content:
            if current_line >= max_lines_per_page:
                # Inicia uma nova página quando atinge o limite de linhas
                c.showPage()
                y_position = page_height - margin
                current_line = 0

            # Adiciona a linha atual no PDF
            c.drawString(margin, y_position, line.strip())
            y_position -= line_height
            current_line += 1
        c.save()

        # Read and encode the generated PDF
        with open(temp_pdf_path, 'rb') as pdf_file:
            arquivo_binario = pdf_file.read()
            arquivo_base64 = base64.b64encode(arquivo_binario)
           

        # Clean up temporary file
        os.remove(temp_pdf_path)
        # Verificar se o arquivo já está presente nos anexos
        
        existente = self._file_attachment_exist( nome_arquivo.replace(".txt",".pdf") )
        if existente:
            if len(existente.datas) != len(arquivo_base64):
                _logger.info("Arquivo é diferente, atualizando")
                existente.write({'datas': arquivo_base64})
                return existente
            else:
                _logger.info("Arquivo é igual, não faz nada")
                return existente

        attachment = self.env['ir.attachment'].create({
            'name': nome_arquivo.replace(".txt",".pdf"),
            'datas': arquivo_base64,
            'res_model': 'steril_supervisorio.ciclos',
            'res_id': self.id,
            'type': 'binary',
        })
       
       
        self.write({'message_main_attachment_id' : attachment.id } )         
        return attachment
 

    def mount_fig_chart_matplot(self):
       
        
        data = self.get_data_sanitized()
        if not data:
            return None
        range_max = 34
        range_min = 30
        _logger.debug(data)

        colocacao_sensores = self.calcular_colocacoes_por_canal(data, range_min)
        _logger.debug(colocacao_sensores)
        

        # Extraindo os tempos (eixo X) e as temperaturas de cada canal (eixo Y)
        times = [str(entry[0]) for entry in data]
        if len(times) < 1:
            return
        temperatures = [entry[1:] for entry in data]  # Remove o tempo, mantendo apenas as temperaturas

        # Calcular o tempo total
        total_time = self.calculate_total_time(times)

        # Calcular o tempo total em que todas as temperaturas ficaram entre 30 e 34 graus
        time_in_range = self.calculate_time_in_range(times, temperatures, range_min, range_max)
        print(f"Tempo em que todas as temperaturas ficaram entre 30 e 34 graus: {time_in_range[0]} horas, {time_in_range[1]} minutos e {time_in_range[2]} segundos")

        # Determinar a primeira hora em que todas as temperaturas excederam 30 graus
        first_time_above_30 = self.find_time_all_above(times, temperatures, range_min)
        print(f"Primeira hora em que todas as temperaturas excederam 30 graus: {first_time_above_30}")
        

        # Transpor os dados para organizar as temperaturas por canal
        channels = list(zip(*temperatures))

        # Configurar o gráfico
        plt.figure(figsize=(16, 9))

        # Configurar a escala do eixo Y
        min_temp = 20  # Menor temperatura
        max_temp = 36  # Maior temperatura

        plt.ylim(min_temp - 1, max_temp + 1)  # Adicionar margem de 1 unidade
        # Gerar um linspace fixo para o eixo X
        y_ticks = np.linspace(start=min_temp, stop=max_temp,num=(max_temp - min_temp)*2+1)  # 100 divisões fixas
        x_ticks = np.linspace(0, len(times) - 1, num=100, dtype=int)  # 100 divisões fixas
        x_labels = [times[i] for i in x_ticks]  # Selecionar os rótulos correspondentes

        # Plotar cada canal com uma cor diferente
        colors = ["b", "g", "r", "c", "m", "y", "k", "orange"]  # Lista de cores para os canais
        for i, channel_temps in enumerate(channels):
            plt.plot([index for index,t in enumerate(times)], channel_temps, label=f"TC{i + 1:02d}", color=colors[i])

        # Ajustar o layout do gráfico
        plt.title(f"{self.name} Temperatures Trend")
        plt.xlabel("Time")
        plt.ylabel("Temperature (°C)")
        plt.xticks(ticks=x_ticks, labels=x_labels,rotation=90)  # Rotacionar os rótulos do eixo X para melhor leitura
        plt.yticks(ticks=y_ticks)  # Rotacionar os rótulos do eixo X para melhor leitura
        plt.legend()  # Mostrar a legenda para identificar os canais
        plt.grid(True)

        

        # # Adicionar o tempo total no canto inferior direito do gráfico
        # total_time_text = f"Total Time: {total_time[0]}h {total_time[1]}m {total_time[2]}s"
        # plt.gcf().text(0.95, 0.12, total_time_text, fontsize=10, ha='right', va='bottom')

        # Adicionar caixa de texto com dados estatísticos
        str_colocacao = ""
        for channel, tempo, temperatura in colocacao_sensores:
            str_colocacao += f"TC{channel:02d} - {tempo} \n"

        stats_text = (
            f"Total Time: {total_time[0]}h {total_time[1]}m {total_time[2]}s\n"
            f"Time in the range [{range_min}-{range_max}°C]: {time_in_range[0]}h {time_in_range[1]}m {time_in_range[2]}s\n"
            f"Start times (\u2265{range_min}°C):\n"
            f"{str_colocacao}"
            
            
            
        )
        plt.gcf().text(0.25, 0.25, stats_text, fontsize=10, ha='left',va='center', bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

        # Adicionando uma linha vertical em 30 graus
        plt.axhline(y=range_max, color='r', linestyle='--', linewidth=2)
        plt.axhline(y=range_min, color='r', linestyle='--', linewidth=2)
        # Exibir o gráfico
        plt.tight_layout()
        
        return plt
    
    def plot_temperature_histograms(self):
        data = self.get_data_sanitized()
        range_max = 34
        range_min = 30
        # Extraindo os tempos (eixo X) e as temperaturas de cada canal (eixo Y)
        times = [str(entry[0]) for entry in data]
        if len(times) < 1:
            return
        temperatures = [entry[1:] for entry in data]  # Remove o tempo, mantendo apenas as temperaturas

        data_t = np.array([t[1:] for t in temperatures])
        plt.figure(figsize=(16, 6))
        for i in range(data_t.shape[1]):
            plt.hist(data_t[:, i], bins=40, alpha=0.5, label=f'TC{i+1:02d}')
        
        plt.title('Temperature Distribution of Each Sensor')
        plt.xlabel('Temperature (°C)')
        plt.ylabel('Frequency')
        plt.axvline(x=range_max, color='r', linestyle='--', linewidth=2)
        plt.axvline(x=range_min, color='r', linestyle='--', linewidth=2)
        x_ticks = np.linspace(start=20, stop=36,num=(36 - 20)*2+1) 
        plt.xticks(ticks=x_ticks)
        plt.legend()
        plt.xlim(20, 36)
        plt.tight_layout()
        return plt

    def set_chart_image(self):
        for rec in self:
            ### GRAFICO TREND
            _logger.debug("Gerando grafico tempo...")
            fig = rec.mount_fig_chart_matplot()
            if not fig:
                _logger.debug("Não foi possível salvar imagem do gráfico, erro na montagem com os dados da fita!")
                return False
            _logger.debug("Grafico gerado!")
           
            # # Convertendo a imagem PNG em dados binários
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png')
            buffer.seek(0) 
            #pyo.plot_mpl()
            _logger.debug("Transformado em figura")
           

            _logger.debug("Colocando no banco de dados")
            rec.grafico_ciclo = base64.b64encode(buffer.read())
            
            ### GRAFICO HISTOGRAMA
            _logger.debug("Gerando grafico distribuição...")
            fig = rec.plot_temperature_histograms()
            if not fig:
                _logger.debug("Não foi possível salvar imagem do gráfico DISTRIBUICAO, erro na montagem com os dados da fita!")
                return False
            _logger.debug("Grafico distribuição gerado!")
           
            # # Convertendo a imagem PNG em dados binários
            buffer = io.BytesIO()
            fig.savefig(buffer, format='png')
            buffer.seek(0) 
            #pyo.plot_mpl()
            _logger.debug("Transformado em figura")
           

            _logger.debug("Colocando no banco de dados")
            rec.grafico_ciclo_distribuition = base64.b64encode(buffer.read())



        