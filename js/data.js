/* Shared content: apartments & experiences. Coordinates are approximate
   reference points for each neighbourhood, meant for the map embeds. */

const APARTMENTS = [
  {
    id: "wayaca-ocean",
    name: "Suite Wayaca Ocean",
    city: "aruba",
    cityLabel: "Aruba",
    zone: "Wayaca, Aruba",
    tile: "tile-1",
    price: 185,
    beds: 2,
    lat: 12.5250,
    lng: -69.9683,
    distances: [
      { icon: "beach", label: "Playa Baby Beach", time: "4 min" },
      { icon: "plane", label: "Aeropuerto AUA", time: "15 min" },
      { icon: "pin", label: "Centro San Nicolas", time: "6 min" },
    ],
  },
  {
    id: "wayaca-sunset",
    name: "Loft Wayaca Sunset",
    city: "aruba",
    cityLabel: "Aruba",
    zone: "Wayaca, Aruba",
    tile: "tile-3",
    price: 145,
    beds: 1,
    lat: 12.5201,
    lng: -69.9629,
    distances: [
      { icon: "beach", label: "Rodgers Beach", time: "5 min" },
      { icon: "plane", label: "Aeropuerto AUA", time: "14 min" },
      { icon: "pin", label: "Centro San Nicolas", time: "5 min" },
    ],
  },
  {
    id: "el-prado-boutique",
    name: "Apartamento El Prado Boutique",
    city: "barranquilla",
    cityLabel: "Barranquilla",
    zone: "El Prado, Barranquilla",
    tile: "tile-2",
    price: 95,
    beds: 2,
    lat: 10.9954,
    lng: -74.7898,
    distances: [
      { icon: "beach", label: "Puerto Colombia", time: "25 min" },
      { icon: "plane", label: "Aeropuerto Cortissoz", time: "20 min" },
      { icon: "pin", label: "Centro histórico", time: "8 min" },
    ],
  },
  {
    id: "buenavista-skyline",
    name: "Penthouse Buenavista Skyline",
    city: "barranquilla",
    cityLabel: "Barranquilla",
    zone: "Buenavista, Barranquilla",
    tile: "tile-4",
    price: 140,
    beds: 3,
    lat: 10.9878,
    lng: -74.7944,
    distances: [
      { icon: "beach", label: "Puerto Colombia", time: "22 min" },
      { icon: "plane", label: "Aeropuerto Cortissoz", time: "25 min" },
      { icon: "pin", label: "Centro histórico", time: "12 min" },
    ],
  },
];

const EXPERIENCES = {
  aruba: [
    {
      name: "Snorkel en Baby Beach",
      desc: "Aguas tranquilas y arrecife accesible desde la orilla.",
      tile: "tile-1",
      lat: 12.4239,
      lng: -69.8987,
      time: "10 min desde Suite Wayaca Ocean",
    },
    {
      name: "Atardecer en Rodgers Beach",
      desc: "La postal favorita de los locales al caer el sol.",
      tile: "tile-5",
      lat: 12.4368,
      lng: -69.9052,
      time: "5 min desde Loft Wayaca Sunset",
    },
    {
      name: "Ruta de arte en San Nicolas",
      desc: "Murales, galerías y cocina callejera del sur de la isla.",
      tile: "tile-3",
      lat: 12.4453,
      lng: -69.9075,
      time: "6 min desde ambos apartamentos",
    },
  ],
  barranquilla: [
    {
      name: "Malecón del Río",
      desc: "Paseo junto al Magdalena, ideal al atardecer.",
      tile: "tile-2",
      lat: 10.9691,
      lng: -74.7736,
      time: "15 min desde El Prado Boutique",
    },
    {
      name: "Museo del Carnaval",
      desc: "La historia del Carnaval de Barranquilla, Patrimonio de la Humanidad.",
      tile: "tile-6",
      lat: 10.9908,
      lng: -74.7970,
      time: "10 min desde El Prado Boutique",
    },
    {
      name: "Playas de Puerto Colombia",
      desc: "El muelle histórico y arena frente al Caribe.",
      tile: "tile-4",
      lat: 10.9878,
      lng: -74.9555,
      time: "25 min desde Buenavista Skyline",
    },
  ],
};

const TESTIMONIALS = [
  {
    quote: "El apartamento en Wayaca tenía mejor vista que cualquier hotel donde nos hayamos quedado. Volveremos.",
    author: "Marianela R. · Suite Wayaca Ocean",
  },
  {
    quote: "Reservar fue clarísimo, el resumen con el mapa nos ayudó a entender exactamente dónde íbamos a quedarnos.",
    author: "Julián C. · El Prado Boutique",
  },
  {
    quote: "Detalles de hotel de lujo con la comodidad de tener cocina propia. El penthouse en Buenavista superó todo.",
    author: "Sofía A. · Penthouse Buenavista Skyline",
  },
  {
    quote: "La ubicación en San Nicolas nos dejó caminando a la playa en minutos. Atención impecable.",
    author: "Daniel M. · Loft Wayaca Sunset",
  },
];
