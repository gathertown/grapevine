interface ServiceSelectorProps {
  selectedService: string;
  onServiceChange: (service: string) => void;
}

const services = [
  { id: 'ssm', name: 'SSM Parameters' },
  { id: 'sqs', name: 'SQS Queues' },
];

export function ServiceSelector({ selectedService, onServiceChange }: ServiceSelectorProps) {
  return (
    <div className="service-selector">
      <h3>Services</h3>
      {services.map((service) => (
        <button
          key={service.id}
          className={`service-item ${selectedService === service.id ? 'active' : ''}`}
          onClick={() => onServiceChange(service.id)}
        >
          {service.name}
        </button>
      ))}
    </div>
  );
}
