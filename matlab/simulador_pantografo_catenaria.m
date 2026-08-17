% simulador_pantografo_catenaria.m
%
% Modela a interacao dinamica pantografo-catenaria por um sistema
% massa-mola-amortecedor de 2 graus de liberdade, o modelo classico usado
% na literatura de monitoramento de catenaria (ver README, secao
% "Referencias" -- Ritzberger et al. 2023 e o mapeamento sistematico da
% Sensors 2024 usam esse tipo de modelo simplificado como base).
%
% NAO RODEI ESTE SCRIPT: nao ha MATLAB nem Octave disponivel no ambiente
% onde o resto do projeto foi desenvolvido. Rode no seu MATLAB e me
% avise se aparecer erro ou resultado estranho, pra eu corrigir.
%
% Fisica do modelo:
%
%   Pantografo = dois corpos rigidos ligados por mola-amortecedor:
%     - cabeca (m1): toca o fio de contato
%     - armacao (m2): recebe a forca de elevacao do atuador (F0), a
%       forca que empurra o pantografo pra cima contra o cabo
%
%   Catenaria = representada como uma rigidez k_c(t) que varia com a
%   posicao do pantografo ao longo do vao entre dois suportes: mais
%   rigida perto dos suportes (o cabo tem menos folga pra ceder ali),
%   mais mole no meio do vao. Essa variacao periodica é o que gera a
%   oscilacao real da forca de contato mesmo com velocidade constante,
%   nao é ruido, é geometria.
%
%   Equacoes de movimento (Newton, 2 GDL):
%     m1*z1'' + c1*(z1'-z2') + k1*(z1-z2) + k_c(t)*z1 = 0
%     m2*z2'' + c1*(z2'-z1') + k1*(z2-z1) - c2*z2' - k2*z2 = -F0
%
%   A forca de contato instantanea é F_contato(t) = k_c(t) * z1(t), a
%   metrica de "Forca de Elevacao (Uplift Force)" que a sugestao de
%   métricas avancadas mencionava numa sessao anterior.
%
% IMPORTANTE: no MATLAB, funcoes locais num arquivo de script precisam
% ficar no FINAL do arquivo, depois de todo o codigo executavel (regra
% do parser, nao estilo). Por isso as duas funcoes deste script,
% rigidez_catenaria() e equacoes(), ficam la embaixo.

clear; clc;

%% Parametros do pantografo (valores tipicos de literatura, em ordem de grandeza)
m1 = 7.2;      % kg, massa da cabeca (contato direto com o fio)
m2 = 6.0;      % kg, massa da armacao
c1 = 40;       % N*s/m, amortecimento entre cabeca e armacao
k1 = 4200;     % N/m, rigidez entre cabeca e armacao
c2 = 70;       % N*s/m, amortecimento do atuador da armacao
k2 = 6000;     % N/m, rigidez residual do atuador (ver nota abaixo)
F0 = 90;       % N, forca de elevacao nominal do atuador

% Nota sobre k2: com valor baixo demais (testei 80 N/m antes de ajustar),
% o deslocamento estatico da armacao (~F0/k2) passava de 1 metro, fora de
% qualquer realidade fisica de pantografo. 6000 N/m da um deslocamento
% estatico de ~15mm, ordem de grandeza plausivel.

%% Parametros da catenaria
L_vao = 60;              % m, comprimento do vao entre suportes (tipico ferrovia)
k_c_medio = 2200;        % N/m, rigidez media do fio de contato
variacao_rigidez = 0.35; % fracao de variacao entre suporte e meio-vao

%% Parametros de operacao
velocidade_kmh = 160;
velocidade_ms = velocidade_kmh / 3.6;
duracao_s = 2 * L_vao / velocidade_ms;   % tempo pra atravessar 2 vaos

%% Integracao numerica
x0 = [0; 0; 0; 0];  % repouso: [z1, z1', z2, z2']
opcoes = odeset('RelTol', 1e-8, 'AbsTol', 1e-10);
[t, x] = ode45(@(t, x) equacoes(t, x, m1, m2, c1, k1, c2, k2, F0, ...
    velocidade_ms, L_vao, k_c_medio, variacao_rigidez), ...
    [0 duracao_s], x0, opcoes);

z1 = x(:, 1);

%% Forca de contato: F = k_c(t) * z1(t) + F0
k_c_vetor = arrayfun(@(tt) rigidez_catenaria(tt, velocidade_ms, L_vao, k_c_medio, variacao_rigidez), t);
forca_contato = k_c_vetor .* z1 + F0;  % + F0 porque a forca estatica de repouso ja empurra o cabo

%% Metricas
forca_media = mean(forca_contato);
forca_max = max(forca_contato);
forca_min = min(forca_contato);
desvio_padrao = std(forca_contato);
coef_variacao = desvio_padrao / forca_media;

fprintf('=== Simulacao pantografo-catenaria ===\n');
fprintf('Velocidade: %.0f km/h\n', velocidade_kmh);
fprintf('Duracao simulada: %.2f s (%d vaos)\n', duracao_s, 2);
fprintf('\n--- Forca de contato ---\n');
fprintf('Media: %.1f N\n', forca_media);
fprintf('Minima: %.1f N\n', forca_min);
fprintf('Maxima: %.1f N\n', forca_max);
fprintf('Desvio padrao: %.1f N\n', desvio_padrao);
fprintf('Coeficiente de variacao: %.3f\n', coef_variacao);
fprintf('\nReferencia EN 50318/normas de qualidade de captacao: coeficiente\n');
fprintf('de variacao da forca de contato deve ficar tipicamente abaixo de\n');
fprintf('0.3 para nao comprometer a qualidade de captacao de corrente.\n');

%% Graficos
figure('Name', 'Interacao Pantografo-Catenaria');

subplot(3, 1, 1);
plot(t, z1 * 1000, 'b-', 'LineWidth', 1.2);
xlabel('Tempo (s)');
ylabel('Deslocamento (mm)');
title('Deslocamento vertical da cabeca do pantografo');
grid on;

subplot(3, 1, 2);
plot(t, k_c_vetor, 'r-', 'LineWidth', 1.2);
xlabel('Tempo (s)');
ylabel('Rigidez (N/m)');
title('Rigidez da catenaria ao longo do vao (mais mole no meio, mais rigida nos suportes)');
grid on;

subplot(3, 1, 3);
plot(t, forca_contato, 'k-', 'LineWidth', 1.2);
hold on;
yline(forca_media, 'g--', 'Media');
xlabel('Tempo (s)');
ylabel('Forca de contato (N)');
title('Forca de contato pantografo-catenaria');
grid on;

%% Exporta serie temporal pra eventual uso no simulador Python
% (nao integrado automaticamente ao pipeline, so exporta o CSV; se quiser
% usar essa forca real em vez do uniform(3000,9000) que
% src/simulador/sensor.py:ler() usa hoje pra amplitude de passagem de
% trem, precisa de um passo manual de importar esse CSV la)
tabela = table(t, forca_contato, z1, k_c_vetor, ...
    'VariableNames', {'tempo_s', 'forca_contato_n', 'deslocamento_m', 'rigidez_n_m'});
writetable(tabela, 'forca_contato_simulada.csv');
fprintf('\nSerie temporal exportada para forca_contato_simulada.csv\n');

%% ===== Funcoes locais (precisam ficar no final do arquivo) =====

function k = rigidez_catenaria(t, velocidade_ms, L_vao, k_c_medio, variacao_rigidez)
    % Rigidez minima no meio do vao, maxima nos suportes (extremos).
    posicao_no_vao = mod(velocidade_ms * t, L_vao);
    fase = 2 * pi * posicao_no_vao / L_vao;
    k = k_c_medio * (1 - variacao_rigidez * cos(fase));
end

function dxdt = equacoes(t, x, m1, m2, c1, k1, c2, k2, F0, velocidade_ms, L_vao, k_c_medio, variacao_rigidez)
    % Estado x = [z1; z1'; z2; z2'], z1 = cabeca, z2 = armacao.
    z1 = x(1); v1 = x(2);
    z2 = x(3); v2 = x(4);

    k_c = rigidez_catenaria(t, velocidade_ms, L_vao, k_c_medio, variacao_rigidez);

    a1 = (-c1*(v1 - v2) - k1*(z1 - z2) - k_c*z1) / m1;
    a2 = (-c1*(v2 - v1) - k1*(z2 - z1) + c2*v2 + k2*z2 - F0) / m2;

    dxdt = [v1; a1; v2; a2];
end
