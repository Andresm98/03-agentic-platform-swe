output "folder_uid" {
  description = "UID de la carpeta de Grafana con los dashboards."
  value       = grafana_folder.agentic.uid
}

output "dashboard_urls" {
  description = "Ruta de cada dashboard en Grafana, por fichero JSON."
  value       = { for file, d in grafana_dashboard.this : file => d.url }
}
