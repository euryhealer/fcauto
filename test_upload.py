import pandas as pd
import requests

df = pd.DataFrame({ SKU: [ABC-RED-10], NOMBRE: [Test Item], FOTO: [foo.jpg]})
path = 'test_upload.xlsx'
df.to_excel(path, index=False)
with open(path, 'rb') as f:
    r = requests.post('http://127.0.0.1:8000/api/import', files={'file': ('test_upload.xlsx', f, 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')})
print(r.status_code)
print(r.text)
