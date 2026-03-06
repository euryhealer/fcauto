const App = () => (
  <section className="space-y-3">
    <h1 className="text-2xl font-semibold">Woo Sync MVP</h1>
    <p className="text-slate-700">
      Importa Excel y sincroniza productos variables con WooCommerce.
    </p>
    <ul className="list-disc ml-5 text-slate-700">
      <li>Configura credenciales (Woo, WP Media, Google Drive)</li>
      <li>Importa Excel con columnas SKU, NOMBRE, PRECIO, STOCK, FOTO</li>
      <li>Ejecuta sync y sigue el progreso en vivo</li>
    </ul>
  </section>
);

export default App;
