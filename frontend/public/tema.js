// Tema scelto dall'utente, applicato prima del primo paint (niente lampo di tema sbagliato).
try {
  var t = localStorage.getItem("tema");
  if (t === "chiaro" || t === "scuro") document.documentElement.dataset.tema = t;
} catch (e) {}
