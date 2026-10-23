/* La chiave del Wi-Fi verso il motore dal vivo (porta 8777).
 *
 * Il tablet entra dal QR dell'hub con `?k=`, e il guardiano la ricorda nel
 * cookie `hone_key`. I cookie non guardano la porta: lo stesso cookie vale
 * anche per la 8777. Ma la pagina sta sulla 8778, quindi per il browser la
 * 8777 e' un'altra origine, e una fetch o un XHR cross-origin senza
 * credenziali non manda i cookie. Per questo ogni URL verso la 8777 passa da
 * qui e si porta dietro `k=`. L'handshake del WebSocket i cookie li manda; il
 * `k=` li' e' una cintura in piu', e tiene la stessa regola per tutti gli URL.
 * Sul PC il cookie non c'e' (il PC non porta chiavi) e l'URL resta com'e'.
 *
 * ES3 apposta, come lo script di rinvio di engineer.html: la carica anche il
 * tablet (iPad 3, Safari 9), e niente regex con lookbehind.
 */
(function () {
  function key() {
    var parts = String(document.cookie || "").split(";");
    for (var i = 0; i < parts.length; i++) {
      var p = parts[i].replace(/^\s+/, "");
      // Il nome intero col suo `=`: `xhone_key` non e' il nostro.
      if (p.indexOf("hone_key=") === 0) return p.substring(9);
    }
    return "";
  }

  window.honeLive = function (url) {
    var k = key();
    if (!k) return url;
    return url + (url.indexOf("?") === -1 ? "?" : "&") + "k=" + encodeURIComponent(k);
  };
})();
