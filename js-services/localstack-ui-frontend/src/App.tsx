import { useState } from 'react';
import { ServiceSelector } from './components/ServiceSelector';
import { SSMParameterList } from './components/SSMParameterList';
import { SQSQueueList } from './components/SQSQueueList';

function App() {
  const [selectedService, setSelectedService] = useState('ssm');

  const renderMainContent = () => {
    switch (selectedService) {
      case 'ssm':
        return <SSMParameterList />;
      case 'sqs':
        return <SQSQueueList />;
      default:
        return <div>Select a service from the sidebar</div>;
    }
  };

  return (
    <div className="container">
      <div className="sidebar">
        <h1 style={{ color: '#fff', fontSize: '1.5rem', marginBottom: '2rem' }}>LocalStack UI</h1>
        <ServiceSelector selectedService={selectedService} onServiceChange={setSelectedService} />
      </div>
      <div className="main-content">{renderMainContent()}</div>
    </div>
  );
}

export { App };
