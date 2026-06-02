/**
 * 小程序 App 入口
 */
import { Component, PropsWithChildren } from 'react';
import './app.scss';

class App extends Component<PropsWithChildren> {
  componentDidMount() {
    console.log('🏰 安幕诺家族 · 小红 小程序启动');
  }

  render() {
    return this.props.children;
  }
}

export default App;
