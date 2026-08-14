// Package ingestao recebe e agrega leituras de sensores de catenária.
//
// O contrato de dados é o mesmo NDJSON que o simulador em Python já produz
// (src/simulador/transporte.py): um objeto JSON por linha, um sensor por
// linha. Isso significa que trocar o simulador Python por sensores reais
// depois não muda nada aqui, só quem está do outro lado da conexão TCP.
package ingestao

// Leitura espelha exatamente os campos de LeituraSensor em
// src/simulador/sensor.py. Os nomes dos campos JSON usam snake_case de
// propósito, para bater com o que o `dataclasses.asdict` do Python gera.
type Leitura struct {
	SensorID        string    `json:"sensor_id"`
	KM              float64   `json:"km"`
	Timestamp       float64   `json:"timestamp"`
	TensaoMecanicaN float64   `json:"tensao_mecanica_n"`
	TemperaturaC    float64   `json:"temperatura_c"`
	DanoAcumulado   float64   `json:"dano_acumulado"`
	Estado          string    `json:"estado"`
	Vibracao        []float64 `json:"vibracao"`
}
