import * as React from "react";
import type { SVGProps } from "react";
import { memo } from "react";
const SvgUserWaves = (props: SVGProps<SVGSVGElement>) => <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" {...props}><path d="M2.99921 19.0029C2.99976 16.8378 4.75476 15.0828 6.91984 15.0823H10.8405C13.0055 15.0828 14.7606 16.8378 14.7611 19.0029M19.6952 4.99707C21.4439 6.74578 21.4439 9.58099 19.6952 11.3297M16.7209 6.58073C17.5953 7.45509 17.5953 8.87269 16.7209 9.74705M12.131 8.49853C12.131 10.2942 10.6753 11.7499 8.87966 11.7499C7.08398 11.7499 5.6283 10.2942 5.6283 8.49853C5.6283 6.70286 7.08398 5.24717 8.87966 5.24717C10.6753 5.24717 12.131 6.70286 12.131 8.49853Z" stroke="currentColor" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" /></svg>;
const Memo = memo(SvgUserWaves);
export default Memo;