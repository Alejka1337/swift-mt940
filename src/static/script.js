document.getElementById('convertBtn').addEventListener('click', async () => {
  const fileInput = document.getElementById('csvFile');
  if (!fileInput.files.length) return alert('Выберите файл CSV!');
  const formData = new FormData();
  formData.append('file', fileInput.files[0]);

  const response = await fetch('/convert', { method: 'POST', body: formData });
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'mt940.txt';
  a.click();
});
