// Despertador dos robôs da InfoBolsa (Google Apps Script).
// Chama os robôs do GitHub na hora certa, porque o horário automático do próprio GitHub atrasa ou pula rodadas.
// A chave do GitHub fica em Configurações do projeto > Propriedades do script, com o nome GITHUB_TOKEN.

const REPO = 'InfoBolsaInvest/cotacoes';
const FUSO = 'America/Sao_Paulo';

function chama(robo, entradas) {
  const chave = PropertiesService.getScriptProperties().getProperty('GITHUB_TOKEN');
  if (!chave) throw new Error('Falta a propriedade GITHUB_TOKEN nas configurações do projeto.');
  const r = UrlFetchApp.fetch('https://api.github.com/repos/' + REPO + '/actions/workflows/' + robo + '/dispatches', {
    method: 'post',
    contentType: 'application/json',
    muteHttpExceptions: true,
    headers: { Authorization: 'Bearer ' + chave, Accept: 'application/vnd.github+json' },
    payload: JSON.stringify({ ref: 'main', inputs: entradas || {} })
  });
  if (r.getResponseCode() !== 204) {
    throw new Error(robo + ': GitHub respondeu ' + r.getResponseCode() + ' ' + r.getContentText().slice(0, 300));
  }
}

function relogio() {
  const agora = new Date();
  const hora = Utilities.formatDate(agora, FUSO, 'HH:mm');
  const dia = Utilities.formatDate(agora, FUSO, 'yyyy-MM-dd');
  const semana = Number(Utilities.formatDate(agora, FUSO, 'u')); // 1 = segunda ... 7 = domingo
  const memoria = PropertiesService.getScriptProperties();

  // Cotações: de 10 em 10 minutos durante o pregão
  if (semana <= 5 && hora >= '10:00' && hora <= '18:40') chama('atualiza.yml');

  // Notícias: 7h30 (com portais) e 19h (só documentos oficiais), uma vez cada por dia
  if (hora >= '07:30' && memoria.getProperty('manha') !== dia) {
    chama('noticias.yml', { turno: 'manha' });
    memoria.setProperty('manha', dia);
  }
  if (hora >= '19:00' && memoria.getProperty('noite') !== dia) {
    chama('noticias.yml', { turno: 'noite' });
    memoria.setProperty('noite', dia);
  }
}

// Rodar uma vez para ligar o despertador (de 10 em 10 minutos).
function instalar() {
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('relogio').timeBased().everyMinutes(10).create();
  const agora = Utilities.formatDate(new Date(), FUSO, 'yyyy-MM-dd');
  const memoria = PropertiesService.getScriptProperties();
  // não repete hoje as rodadas de notícias que já aconteceram
  if (Utilities.formatDate(new Date(), FUSO, 'HH:mm') >= '07:30') memoria.setProperty('manha', agora);
  if (Utilities.formatDate(new Date(), FUSO, 'HH:mm') >= '19:00') memoria.setProperty('noite', agora);
  chama('atualiza.yml'); // teste: se der erro aqui, a chave do GitHub não está certa
}
